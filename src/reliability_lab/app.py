from __future__ import annotations

import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from reliability_lab.cache import ResponseCache, SharedRedisCache
from reliability_lab.circuit_breaker import CircuitBreaker, CircuitState
from reliability_lab.gateway import ReliabilityGateway
from reliability_lab.providers import FakeLLMProvider

app = FastAPI(title="Reliability Gateway Dashboard")

# Global gateway state
primary_provider = FakeLLMProvider("primary", fail_rate=0.25, base_latency_ms=180, cost_per_1k_tokens=0.01)
backup_provider = FakeLLMProvider("backup", fail_rate=0.05, base_latency_ms=260, cost_per_1k_tokens=0.006)

providers = [primary_provider, backup_provider]

breakers = {
    "primary": CircuitBreaker(name="primary", failure_threshold=3, reset_timeout_seconds=5.0),
    "backup": CircuitBreaker(name="backup", failure_threshold=3, reset_timeout_seconds=5.0),
}

# Determine if Redis is available, fallback to memory
redis_url = "redis://localhost:6379/0"
cache = None
cache_type = "none"

try:
    import redis
    r = redis.Redis.from_url(redis_url)
    r.ping()
    cache = SharedRedisCache(redis_url, ttl_seconds=300, similarity_threshold=0.92)
    cache_type = "redis"
    print("Using Redis Shared Cache for Web App")
except Exception:
    cache = ResponseCache(ttl_seconds=300, similarity_threshold=0.92)
    cache_type = "memory"
    print("Using In-Memory Cache for Web App (Redis connection failed)")

gateway = ReliabilityGateway(providers, breakers, cache)

class CompleteRequest(BaseModel):
    prompt: str
    primary_fail_rate: float
    backup_fail_rate: float
    cache_enabled: bool
    similarity_threshold: float

@app.post("/api/complete")
def complete_prompt(req: CompleteRequest):
    # Apply settings
    primary_provider.fail_rate = req.primary_fail_rate
    backup_provider.fail_rate = req.backup_fail_rate
    
    if req.cache_enabled:
        gateway.cache = cache
        if cache:
            cache.similarity_threshold = req.similarity_threshold
    else:
        gateway.cache = None

    try:
        res = gateway.complete(req.prompt)
        
        # Collect circuit breaker states
        breaker_states = {}
        for name, cb in breakers.items():
            breaker_states[name] = {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "success_count": cb.success_count,
                "transition_log": cb.transition_log[-10:]  # Last 10 log entries
            }
            
        # Collect cache items
        cached_keys = []
        if req.cache_enabled and cache:
            if isinstance(cache, SharedRedisCache):
                for key in cache._redis.scan_iter(f"{cache.prefix}*"):
                    fields = cache._redis.hgetall(key)
                    if "query" in fields:
                        cached_keys.append(fields["query"])
            elif isinstance(cache, ResponseCache):
                cached_keys = [e.key for e in cache._entries]

        return {
            "text": res.text,
            "route": res.route,
            "provider": res.provider,
            "cache_hit": res.cache_hit,
            "latency_ms": round(res.latency_ms, 2),
            "estimated_cost": round(res.estimated_cost, 6),
            "error": res.error,
            "breakers": breaker_states,
            "cached_keys": cached_keys,
            "false_hits": getattr(cache, "false_hit_log", []) if cache else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cache/clear")
def clear_cache():
    if cache:
        if isinstance(cache, SharedRedisCache):
            cache.flush()
        elif isinstance(cache, ResponseCache):
            cache._entries.clear()
            cache.false_hit_log.clear()
    return {"status": "success"}

@app.post("/api/breakers/reset")
def reset_breakers():
    for cb in breakers.values():
        cb.state = CircuitState.CLOSED
        cb.failure_count = 0
        cb.success_count = 0
        cb.opened_at = None
        cb.transition_log.clear()
    return {"status": "success"}

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    static_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(static_file):
        with open(static_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h3>Dashboard HTML file is missing. Please build the static/index.html.</h3>"
