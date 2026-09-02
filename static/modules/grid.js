import { state } from './state.js';
import { dom } from './dom.js';
import { buildCardHTML } from './cards.js?v=4';

let _visibleCards = new Map(); // item_id -> Element
let _items = [];
let _cols = 4;
let _cardWidth = 280;
let _cardHeight = 300;
let _rowHeight = 320;
let _gap = 24;
let _isXS = false;
let _isS = false;
let _isL = false;
let _isXL = false;
let _dimensionsDirty = true;

// Buffer of rows before and after the viewport to avoid blank gaps during fast scrolling
const ROW_BUFFER = 2;

export function setGridItems(items) {
    _items = items || [];
    clearGridDOM();
    _dimensionsDirty = true;
    renderVirtualGrid(true); // force full re-layout
}

export function clearGridDOM() {
    if (dom.grid) dom.grid.innerHTML = "";
    _visibleCards.forEach(el => el.remove());
    _visibleCards.clear();
}

export function initVirtualGrid() {
    if (!dom.scrollContainer) return;
    
    // Wire scroll event with requestAnimationFrame throttling (zero layout thrashing)
    let scrollRaf = null;
    dom.scrollContainer.addEventListener('scroll', () => {
        if (scrollRaf) return;
        scrollRaf = requestAnimationFrame(() => {
            renderVirtualGrid();
            scrollRaf = null;
        });
    }, { passive: true });

    // Mark dirty on container resize
    const resizeObserver = new ResizeObserver(() => {
        _dimensionsDirty = true;
        renderVirtualGrid(true);
    });
    resizeObserver.observe(dom.scrollContainer);

    // Wire custom itemsFetched event
    window.addEventListener('itemsFetched', () => {
        setGridItems(state.items);
    });
}

export function recalcGridDimensions(force = false) {
    if (!dom.scrollContainer || !dom.grid) return;
    if (!_dimensionsDirty && !force) return;

    const scale = parseFloat(dom.gridScale?.value || 1);
    const sizeMode = dom.grid.dataset.size || 'm';
    _isXS = sizeMode === 'xs';
    _isS = sizeMode === 's';
    _isL = sizeMode === 'l';
    _isXL = sizeMode === 'xl';

    let baseWidth = 280;
    _gap = 24;

    if (_isXS) {
        baseWidth = 160;
        _gap = 6;
    } else if (_isS) {
        baseWidth = 220;
        _gap = 14;
    } else if (_isL) {
        baseWidth = 360;
        _gap = 28;
    } else if (_isXL) {
        baseWidth = 460;
        _gap = 32;
    }
    
    const targetWidth = baseWidth * scale;
    const currentWidth = dom.scrollContainer.clientWidth;
    const paddingLeft = 24;
    const paddingRight = 24;
    const availableWidth = Math.max(100, currentWidth - paddingLeft - paddingRight);

    _cols = Math.max(1, Math.round((availableWidth + _gap) / (targetWidth + _gap)));
    
    // Stretch cardWidth to fill available columns edge-to-edge
    _cardWidth = Math.floor((availableWidth - (_cols - 1) * _gap) / _cols);

    // Calculate fixed height for cards depending on display mode
    if (_isXS) {
        _cardHeight = Math.round(_cardWidth * 0.75); // Thumbnail only, absolute hover footer
    } else if (_isS) {
        _cardHeight = Math.round(_cardWidth * 0.75) + 65; // Compact footer
    } else if (_isL || _isXL) {
        _cardHeight = Math.round(_cardWidth * 0.75) + 95; // Spacious footer
    } else {
        _cardHeight = Math.round(_cardWidth * 0.75) + 85; // Standard footer
    }
    
    _rowHeight = _cardHeight + _gap;

    // Apply grid parent properties
    dom.grid.style.position = 'relative';
    dom.grid.style.columnCount = 'auto';
    dom.grid.style.columns = 'none';
    dom.grid.style.columnGap = '0px';
    
    const totalRows = Math.ceil(_items.length / _cols);
    dom.grid.style.height = `${Math.max(0, totalRows * _rowHeight)}px`;
    _dimensionsDirty = false;
}

export function renderVirtualGrid(forceLayout = false) {
    if (!_items || !_items.length) {
        clearGridDOM();
        if (dom.grid) dom.grid.style.height = "0px";
        return;
    }

    if (forceLayout || _dimensionsDirty) {
        recalcGridDimensions(true);
    }

    const scrollTop = dom.scrollContainer.scrollTop;
    const viewportHeight = dom.scrollContainer.clientHeight;

    // Calculate active visible row range
    const startRow = Math.max(0, Math.floor(scrollTop / _rowHeight) - ROW_BUFFER);
    const endRow = Math.min(
        Math.ceil(_items.length / _cols) - 1, 
        Math.floor((scrollTop + viewportHeight) / _rowHeight) + ROW_BUFFER
    );

    const startIdx = startRow * _cols;
    const endIdx = Math.min(_items.length, (endRow + 1) * _cols);

    const visibleItemIds = new Set();
    const fragment = document.createDocumentFragment();

    // Render new/visible items
    for (let i = startIdx; i < endIdx; i++) {
        const item = _items[i];
        if (!item) continue;
        
        visibleItemIds.add(item.id);
        
        const row = Math.floor(i / _cols);
        const col = i % _cols;
        const top = row * _rowHeight;
        const left = col * (_cardWidth + _gap);

        let cardEl = _visibleCards.get(item.id);

        if (!cardEl) {
            // Create element by temporary container parsing
            const temp = document.createElement('div');
            temp.innerHTML = buildCardHTML(item, i);
            cardEl = temp.firstElementChild;
            
            // Set styles for absolute positioning
            cardEl.style.position = 'absolute';
            cardEl.style.margin = '0px';
            
            fragment.appendChild(cardEl);
            _visibleCards.set(item.id, cardEl);
        } else if (forceLayout) {
            // Update data index if force refreshing
            cardEl.dataset.index = i;
        }

        // Apply dynamic sizes and placement with hardware-accelerated transform
        cardEl.style.width = `${_cardWidth}px`;
        cardEl.style.height = `${_cardHeight}px`;
        cardEl.style.transform = `translate3d(${left}px, ${top}px, 0)`;

        // Adjust thumbnail block aspect ratio wrapper height
        const thumbBlock = cardEl.querySelector('.card-thumb');
        if (thumbBlock) {
            thumbBlock.style.height = `${Math.round(_cardWidth * 0.75)}px`;
        }
    }

    if (fragment.children.length > 0) {
        dom.grid.appendChild(fragment);
    }

    // Evict items no longer in viewport range
    _visibleCards.forEach((cardEl, id) => {
        if (!visibleItemIds.has(id)) {
            cardEl.remove();
            _visibleCards.delete(id);
        }
    });
}
