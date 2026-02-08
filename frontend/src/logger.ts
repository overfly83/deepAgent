type Level = "debug" | "info" | "warn" | "error";

const isDebug =
  (import.meta.env.VITE_DEBUG ?? "").toString().toLowerCase() === "true";

const levelOrder: Record<Level, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

class Logger {
  private name: string;
  private minLevel: Level;

  constructor(name: string) {
    this.name = name;
    this.minLevel = isDebug ? "debug" : "info";
  }

  private shouldLog(level: Level) {
    return levelOrder[level] >= levelOrder[this.minLevel];
  }

  debug(message: string, data?: unknown) {
    if (this.shouldLog("debug")) {
      console.debug(`[${this.name}] ${message}`, data ?? "");
    }
  }

  info(message: string, data?: unknown) {
    if (this.shouldLog("info")) {
      console.info(`[${this.name}] ${message}`, data ?? "");
    }
  }

  warn(message: string, data?: unknown) {
    if (this.shouldLog("warn")) {
      console.warn(`[${this.name}] ${message}`, data ?? "");
    }
  }

  error(message: string, data?: unknown) {
    if (this.shouldLog("error")) {
      console.error(`[${this.name}] ${message}`, data ?? "");
    }
  }
}

const cache = new Map<string, Logger>();

export function getLogger(name: string) {
  if (!cache.has(name)) {
    cache.set(name, new Logger(name));
  }
  return cache.get(name)!;
}
