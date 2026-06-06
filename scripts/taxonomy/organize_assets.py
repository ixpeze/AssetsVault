
import sqlite3
import requests
import json
import argparse
import sys
from pathlib import Path
import time

DB_PATH = Path('3dskyfree.db')
OLLAMA_API = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3"

def get_db_connection():
    if not DB_PATH.exists():
        print(f"Error: Database {DB_PATH} not found.")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def check_model_availability(model_name):
    try:
        response = requests.get(OLLAMA_API.replace("/api/generate", "/api/tags"), timeout=5)
        if response.status_code == 200:
            models = [m['name'] for m in response.json().get('models', [])]
            # specific version matching might be tricky (e.g. llama3:latest vs llama3), so loose match
            if any(model_name in m for m in models):
                return True
            print(f"Warning: Model '{model_name}' not found in Ollama.")
            print(f"Available models: {', '.join(models)}")
            print(f"Please run: ollama pull {model_name}")
            return False
    except Exception as e:
        print(f"Could not check models: {e}")
    return True # Assume it might work if we can't check

def api_generate(prompt, model=DEFAULT_MODEL, temperature=0.7):
    """Call Ollama API."""
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "temperature": temperature,
        "format": "json" 
    }
    try:
        response = requests.post(OLLAMA_API, json=data, timeout=120)
        if response.status_code == 404:
            print(f"Error: Model '{model}' not found. Please run 'ollama pull {model}'.")
            return None
        response.raise_for_status()
        result = response.json()
        return json.loads(result.get("response", "{}"))
    except requests.exceptions.RequestException as e:
        print(f"Error calling Ollama: {e}")
        return None
    except json.JSONDecodeError:
        print("Error decoding JSON from Ollama response.")
        return None

def organize_categories(args):
    conn = get_db_connection()
    if not check_model_availability(args.model) and not args.dry_run:
        print("Proceeding anyway, but it might fail.")
    
    cursor = conn.cursor()

    
    # 1. Fetch all categories
    categories = cursor.execute("SELECT id, name, slug, parent_id FROM categories ORDER BY name").fetchall()
    cat_lookup = {c['name'].lower(): {'id': c['id'], 'original_name': c['name']} for c in categories}
    
    print(f"Found {len(categories)} categories. Grouping by Hierarchical Path...")
    
    # We will process in batches and ask for full paths
    batch_size = 30
    cat_names = [c['name'] for c in categories]
    
    proposed_updates = [] # (child_id, parent_id)
    new_categories = [] # (name, slug, parent_name)
    
    # Cache to keep track of created/existing categories during this run to avoid dupes
    # keys are lower case names
    known_cats = cat_lookup.copy()
    
    for i in range(0, len(cat_names), batch_size):
        batch = cat_names[i:i+batch_size]
        print(f"Processing batch {i}/{len(cat_names)}...")
        
        prompt = f"""
        Organize the following 3D asset categories into logical hierarchical paths.
        Use ' > ' to separate levels. 
        Start with a broad Top-Level Category (e.g. Furniture, Lighting, Architecture, Nature, Technology, Characters).
        Target a depth of 2-4 levels.
        
        Format: JSON object where keys are the original category name and values are the path.
        Example: 
        {{
            "Sofa": "Furniture > Seating > Sofas",
            "Oak Tree": "Nature > Plants > Trees > Deciduous"
        }}
        
        Categories to organize:
        {json.dumps(batch)}
        """
        
        response = api_generate(prompt, model=args.model)
        if not response:
            continue
            
        for original_name, path_str in response.items():
            if original_name.lower() not in cat_lookup:
                continue
                
            parts = [p.strip() for p in path_str.split('>')]
            if not parts:
                continue
                
            # Navigate the path, identifying parents
            current_parent_id = 0 # Root
            
            for index, part in enumerate(parts):
                part_lower = part.lower()
                is_last = (index == len(parts) - 1)
                
                # If this part corresponds to the category itself (often the last part)
                # But sometimes "Sofa" -> "Furniture > Seating > Sofa" (matched)
                # Or "Sofa" -> "Furniture > Seating" (Sofa is the item type, so it goes UNDER Seating)
                
                # Actually, we want to set the parent of 'original_name'.
                # The path describes where 'original_name' belongs.
                # If path is "A > B > C", and original is "C", then Parent(C) = B.
                # If path is "A > B", and original is "C", then Parent(C) = B ?? No, usually C is the leaf.
                # Let's assume the Path output INCLUDES the category itself at the end, OR describes the parent path.
                
                # Let's try to match the original name to the last part of the path.
                # If they are close, then the *previous* part is the parent.
                # If they are totally different, maybe the category serves as the leaf under the last part.
                
                # Let's simple treat the path as the structure.
                # We need to ensure A, B exist.
                # Then we set C's parent to B.
                
                # Let's traverse the parts except the last one. The last one is the category itself (or what it should be renamed to).
                # Wait, if "Sofa" -> "Furniture > Sofas", do we rename "Sofa" to "Sofas"? Maybe.
                # But safer to just set parent.
                
                # Strategy:
                # 1. Ensure all parts usually up to len-1 exist.
                # 2. The category 'original_name' is placed under parts[-2].
                # 3. What if parts[-1] != original_name? 
                #    e.g. "Small Chair" -> "Furniture > Seating > Chairs". 
                #    Does "Small Chair" become a child of "Chairs"? YES.
                #    So we ensure "Furniture", "Seating", "Chairs" exist.
                #    Then set Parent("Small Chair") = ID("Chairs").
                
                # So traverse ALL parts in the path. Ensure they exist.
                # The generic logic: The user provided a PATH. The original category belongs to the last node of that path?
                # No, standard is: "Category" belongs to "Path".
                # If I say "Sofa", and LLM gives "Furniture > Seating", then Sofa is child of Seating.
                # If I say "Sofa", and LLM gives "Furniture > Seating > Sofas", then Sofa is child of Sofas? Or is Sofa == Sofas?
                
                # Let's assume the LLM output is the CLASSIFICATION.
                # So "Small Chair" classified as "Furniture > Seating > Chairs".
                # Parent("Small Chair") = "Chairs".
                # We need to make sure "Furniture", "Seating", "Chairs" exist and are linked.
                
                parent_of_chain = 0
                for part_name in parts:
                    p_lower = part_name.lower()
                    
                    # Check if this category exists
                    if p_lower in known_cats:
                        # It exists. We might need to update *its* parent if it was 0 and we are defining structure?
                        # But we are only organizing the LEAF nodes from the input list.
                        # We should be careful not to move "Furniture" under "Characters" accidentally.
                        
                        # We only create/ensure intermediate nodes.
                        cat_id = known_cats[p_lower]['id']
                        
                        # If we just created it in this session, we know its parent.
                        # If it existed before, we trust it? Or we can enforce hierarchy for intermediate nodes too?
                        # For simplicity, if it exists, grab its ID.
                        parent_of_chain = cat_id
                    else:
                        # Create new intermediate category
                        # Check if we already scheduled creation
                        found_new = next((n for n in new_categories if n[0].lower() == p_lower), None)
                        if found_new:
                            # We already planned to create it, but we need its ID? 
                            # We can't get ID until formatted.
                            # So we will do a 2-pass or just create strictly.
                            # For simplicity in this script, we'll just queue it and hope. 
                            # Actually, we need IDs to build the tree.
                            # So let's create them on the fly if not dry_run? 
                            # Or Use placeholders.
                            pass
                        
                        # Let's handle creation logic deferred? No, we need IDs.
                        # If dry-run, we pretend we have an ID.
                        if args.dry_run:
                            fake_id = 999000 + len(new_categories)
                            new_categories.append((part_name, part_name.lower().replace(" ", "-"), parent_of_chain))
                            known_cats[p_lower] = {'id': fake_id}
                            parent_of_chain = fake_id
                        else:
                            # Create immediately
                            slug = part_name.lower().replace(" ", "-")
                            # Check collision on slug
                            try:
                                cursor.execute("INSERT INTO categories (name, slug, parent_id) VALUES (?, ?, ?)", 
                                               (part_name, slug, parent_of_chain))
                                new_id = cursor.lastrowid
                                known_cats[p_lower] = {'id': new_id}
                                parent_of_chain = new_id
                                print(f"Created category: {part_name} (under {parent_of_chain})")
                            except sqlite3.IntegrityError:
                                # Slug exists?
                                existing = cursor.execute("SELECT id FROM categories WHERE slug = ?", (slug,)).fetchone()
                                if existing:
                                    parent_of_chain = existing['id']
                                    known_cats[p_lower] = {'id': existing['id']}

                # Finally, the original category 'original_name' should have parent = parent_of_chain
                # UNLESS 'original_name' IS 'parts[-1]' (e.g. self-match)
                # "Sofa" -> "Furniture > Sofas". Sofa != Sofas (singular vs plural).
                # We want "Sofa" to be child of "Sofas"? Or "Sofa" renamed to "Sofas"?
                # Merging is safer in 'tags'. Here we just set parent.
                
                # If matching exactly, don't self-parent
                child_id = cat_lookup[original_name.lower()]['id']
                if child_id != parent_of_chain:
                     # Check if we are creating a loop? 
                     # (Simple check: parent_of_chain should not be child_id)
                     if parent_of_chain != child_id:
                        proposed_updates.append((child_id, parent_of_chain, original_name, parts[-1]))

    print(f"\nProposed Updates: {len(proposed_updates)}")
    if args.dry_run:
        for cid, pid, cname, pname in proposed_updates[:20]:
            print(f"[Dry Run] '{cname}' -> Parent: '{pname}' (ID: {pid})")
        print(f"[Dry Run] New Categories to be created: {len(new_categories)}")
    else:
        print("Applying updates...")
        count = 0
        for cid, pid, cname, pname in proposed_updates:
            # check loop again
            if cid == pid: continue
            cursor.execute("UPDATE categories SET parent_id = ? WHERE id = ?", (pid, cid))
            count += 1
        conn.commit()
        print(f"Updated {count} categories.")

    conn.close()

def organize_tags(args):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    tags = cursor.execute("SELECT id, name FROM tags").fetchall()
    print(f"Found {len(tags)} tags.")
    
    tag_names = [t['name'] for t in tags]
    
    # Identify variations
    # This is tricky with huge lists. We might need to cluster them or just ask for specific cleanup types.
    # Let's try to ask for "Duplicate groups".
    
    print("Asking LLM to identify synonymous tags...")
    
    # We'll simple sample for now or chunk it.
    # Simplest approach: "Group these tags into lists of synonyms".
    
    batch_size = 100
    merges = [] # (keep_id, delete_id)
    
    valid_tags_map = {t['name']: t['id'] for t in tags}
    
    for i in range(0, len(tags), batch_size):
        batch = tag_names[i:i+batch_size]
        
        prompt_tags = f"""
        Identify lists of synonymous tags from the provided list.
        Return a JSON object with key "synonyms" containing a list of lists.
        Each inner list should contain tags that mean the same thing (e.g. ["automobile", "car", "cars"]).
        Ignore tags that are unique.
        
        Tags:
        {json.dumps(batch)}
        """
        
        res = api_generate(prompt_tags, model=args.model)
        if not res or 'synonyms' not in res:
            continue
            
        for group in res['synonyms']:
            if len(group) < 2: continue
            
            # Heuristic: Keep the shortest, or most common?
            # Let's check counts if possible, but for now shortest length usually is "base". 
            # Actually, "cars" -> "car". "table-lamp" -> "table lamp".
            # Let's pick the one that looks "cleanest" (no dashes if possible, singular).
            # LLM could pick canonical, but logical heuristic:
            
            # Simple heuristic: Sort by length, then alpha.
            # Ideally verify with user or use most frequent.
            
            # Let's assume the first one in the group is canonical for now, or ask LLM to identify canonical.
            # But simpler: just pick the shortest.
            
            group.sort(key=len) 
            canonical = group[0]
            
            if canonical not in valid_tags_map: continue
            keep_id = valid_tags_map[canonical]
            
            for other in group[1:]:
                if other not in valid_tags_map: continue
                delete_id = valid_tags_map[other]
                if keep_id != delete_id:
                    merges.append((keep_id, delete_id, canonical, other))

    print(f"\nProposed Merges: {len(merges)}")
    
    if args.dry_run:
        for kid, did, cname, oname in merges:
             print(f"[Dry Run] Merge '{oname}' -> '{cname}'")
    else:
        print("Applying merges...")
        for kid, did, cname, oname in merges:
            # 1. Update item_tags to point to existing tag
            try:
                cursor.execute("UPDATE OR IGNORE item_tags SET tag_id = ? WHERE tag_id = ?", (kid, did))
                # 2. Delete the old tag
                cursor.execute("DELETE FROM tags WHERE id = ?", (did,))
            except sqlite3.Error as e:
                print(f"Error merging {oname} -> {cname}: {e}")
                
        conn.commit()
        print("Done.")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Smartly organize 3D asset categories and tags.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    cat_parser = subparsers.add_parser("categories", help="Organize categories into hierarchy")
    cat_parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    cat_parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model to use")
    
    tag_parser = subparsers.add_parser("tags", help="Merge synonymous tags")
    tag_parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    tag_parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model to use")
    
    args = parser.parse_args()
    
    if args.command == "categories":
        organize_categories(args)
    elif args.command == "tags":
        organize_tags(args)

if __name__ == "__main__":
    main()
