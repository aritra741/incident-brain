function wsBaseUrl() {
  const origin = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
  if (origin) {
    const u = new URL(origin);
    u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${u.origin}/ws`;
  }
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/ws`;
}

class WebSocketService {
  constructor() {
    this.ws = null;
    this.clientId = `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    this.listeners = new Map();
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
    this._currentIncidentId = null;
    this._connected = false;
  }

  connect() {
    return new Promise((resolve, reject) => {
      try {
        if (this.ws) {
          try { this.ws.close(); } catch {}
          this.ws = null;
        }

        this.ws = new WebSocket(`${wsBaseUrl()}/${this.clientId}`);

        this.ws.onopen = () => {
          console.log('WebSocket connected');
          this.reconnectAttempts = 0;
          this._connected = true;

          // Re-subscribe to current incident if we had one
          if (this._currentIncidentId) {
            this.subscribeToIncident(this._currentIncidentId);
          }

          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            this._notifyListeners(data.type, data);
          } catch (e) {
            console.error('Failed to parse WebSocket message:', e);
          }
        };

        this.ws.onclose = (event) => {
          this._connected = false;
          // Only log if it wasn't a clean close initiated by us
          if (!event.wasClean) {
            console.log('WebSocket disconnected unexpectedly');
            this._attemptReconnect();
          } else {
            console.log('WebSocket closed cleanly');
          }
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          // Don't reject after initial connection - let onclose handle reconnect
          if (!this._connected && this.reconnectAttempts === 0) {
            reject(error);
          }
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  _attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
      setTimeout(() => {
        this.connect().catch(() => {});
      }, this.reconnectDelay * this.reconnectAttempts);
    }
  }

  subscribeToIncident(incidentId) {
    this._currentIncidentId = incidentId;
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'subscribe_incident',
        incident_id: incidentId,
      }));
    }
  }

  unsubscribeFromIncident(incidentId) {
    if (this._currentIncidentId === incidentId) {
      this._currentIncidentId = null;
    }
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'unsubscribe_incident',
        incident_id: incidentId,
      }));
    }
  }

  on(type, callback) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type).add(callback);
    return () => this.off(type, callback);
  }

  off(type, callback) {
    if (this.listeners.has(type)) {
      this.listeners.get(type).delete(callback);
    }
  }

  _notifyListeners(type, data) {
    if (this.listeners.has(type)) {
      this.listeners.get(type).forEach(callback => {
        try {
          callback(data);
        } catch (e) {
          console.error('Listener error:', e);
        }
      });
    }
    if (this.listeners.has('*')) {
      this.listeners.get('*').forEach(callback => {
        try {
          callback(data);
        } catch (e) {
          console.error('Listener error:', e);
        }
      });
    }
  }

  disconnect() {
    this._currentIncidentId = null;
    if (this.ws) {
      try {
        this.ws.close(1000, 'Client disconnecting');
      } catch {}
      this.ws = null;
    }
  }
}

export const wsService = new WebSocketService();
export default wsService;
