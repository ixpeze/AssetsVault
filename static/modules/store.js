/**
 * store.js — reactive state wrapper using Proxy.
 *
 * Existing modules continue importing `state` from './state.js' unchanged.
 * New modules can import { reactiveState, subscribe, unsubscribe } for reactive bindings.
 *
 * Usage:
 *   import { subscribe, reactiveState } from './store.js';
 *   subscribe('loading', (value) => console.log('loading changed to', value));
 *   reactiveState.loading = true;  // triggers all 'loading' subscribers
 */
import { state } from './state.js';

/** @type {Map<string, Set<Function>>} */
const _subscribers = new Map();

/**
 * Subscribe to changes on a specific state key.
 * @param {string} key - The state property to watch
 * @param {Function} fn - Called with (newValue, key) on change
 */
export function subscribe(key, fn) {
    if (!_subscribers.has(key)) {
        _subscribers.set(key, new Set());
    }
    _subscribers.get(key).add(fn);
}

/**
 * Unsubscribe a previously registered listener.
 * @param {string} key
 * @param {Function} fn
 */
export function unsubscribe(key, fn) {
    _subscribers.get(key)?.delete(fn);
}

/** Internal: fire all subscribers for a key */
function _notify(key, value) {
    const fns = _subscribers.get(key);
    if (!fns || fns.size === 0) return;
    for (const fn of fns) {
        try {
            fn(value, key);
        } catch (err) {
            console.error(`[store] Subscriber error for key '${key}':`, err);
        }
    }
}

/**
 * Proxy handler — intercepts property assignments on state and fires subscribers.
 * Reads and other operations are passed through transparently.
 */
const storeHandler = {
    set(target, prop, value) {
        const changed = target[prop] !== value;
        target[prop] = value;
        if (changed) {
            _notify(String(prop), value);
        }
        return true;
    },
    get(target, prop) {
        return target[prop];
    },
    deleteProperty(target, prop) {
        const result = delete target[prop];
        _notify(String(prop), undefined);
        return result;
    },
};

/**
 * Reactive proxy over the shared state object.
 * Write to this exactly like you'd write to state — subscribers are notified.
 */
export const reactiveState = new Proxy(state, storeHandler);
