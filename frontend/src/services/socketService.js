import { io } from "socket.io-client";

// A single managed Socket.IO connection per authenticated session (SRS section 58).
class SocketService {
  constructor() {
    this.socket = null;
    this.state = "DISCONNECTED";
    this.stateHandlers = new Set();
  }

  connect(token) {
    if (this.socket) this.disconnect();
    this._setState("CONNECTING");

    this.socket = io(window.location.origin, {
      path: "/socket.io",
      transports: ["websocket", "polling"],
      auth: { token },
    });

    this.socket.on("connect", () => this._setState("CONNECTED"));
    this.socket.on("disconnect", () => this._setState("DISCONNECTED"));
    this.socket.io.on("reconnect_attempt", () => this._setState("RECONNECTING"));
    this.socket.on("connect_error", (err) => {
      if (String(err?.message || "").includes("auth")) {
        this._setState("AUTHENTICATION_FAILED");
      }
    });
    return this.socket;
  }

  disconnect() {
    if (this.socket) {
      this.socket.removeAllListeners();
      this.socket.disconnect();
      this.socket = null;
    }
    this._setState("DISCONNECTED");
  }

  on(event, handler) {
    this.socket?.on(event, handler);
  }

  off(event, handler) {
    this.socket?.off(event, handler);
  }

  emit(event, payload, ack) {
    this.socket?.emit(event, payload, ack);
  }

  subscribeToTransaction(id) {
    this.emit("transaction:subscribe", { transaction_id: id });
  }

  onStateChange(handler) {
    this.stateHandlers.add(handler);
    handler(this.state);
    return () => this.stateHandlers.delete(handler);
  }

  getConnectionState() {
    return this.state;
  }

  _setState(state) {
    this.state = state;
    this.stateHandlers.forEach((h) => h(state));
  }
}

export const socketService = new SocketService();
