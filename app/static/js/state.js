/* State Management — GoActivity */
const State = {
  currentPage: 'overview',
  events: [],
  accounts: [],
  settings: {},
  health: null,
  syncStatus: null,
  listeners: [],

  set(key, value) {
    this[key] = value;
    this._notify(key);
  },

  on(key, fn) {
    this.listeners.push({ key, fn });
  },

  _notify(key) {
    this.listeners.filter(l => l.key === key).forEach(l => l.fn(this[key]));
  },
};

export default State;
