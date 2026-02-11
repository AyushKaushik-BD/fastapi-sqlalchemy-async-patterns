---
title: "Why Uvicorn Health Checks Fail Under Load (And How to Fix It Properly)"
seoTitle: "Why Uvicorn Health Checks Fail Under Load (And How To Fix It)"
seoDescription: "Kubernetes keeps restarting your FastAPI pods? Learn why blocking the event loop kills health checks and how to split Liveness vs. Readiness probes correct"
datePublished: Wed Feb 11 2026 07:54:39 GMT+0000 (Coordinated Universal Time)
cuid: cmlhqi4ae000002jv27th68p0
slug: uvicorn-health-check-failure-kubernetes-fix
cover: https://cdn.hashnode.com/res/hashnode/image/upload/v1770796236385/0400beac-eff1-4c5a-8cb2-bfb0622f3d2c.png
ogImage: https://cdn.hashnode.com/res/hashnode/image/upload/v1770796446394/d4b642e2-116d-4435-802f-b4c08803042f.png
tags: backend, health-cjaeh844x02vvo3wtj5r2s75q, fastapi, programming-tips, uvicorn

---

You deploy your FastAPI app to Kubernetes (or ECS).  
You configure a liveness probe on `/health`.  
Everything looks green.

Then traffic spikes.

Pods start restarting.

`CrashLoopBackOff`.

You check logs:

* No Python exceptions
    
* No OOM
    
* CPU high, but not maxed
    
* Memory stable
    

So why did Kubernetes kill a healthy process?

Because your application was too busy working to answer one simple question:

> “Are you alive?”

## The Real Problem: Event Loop Starvation

Uvicorn runs your FastAPI app on a single-threaded event loop.

That means every request — including your health check — waits its turn.

Think of it this way:

You have one cashier.

* Customer A → heavy DB query
    
* Customer B → CPU-heavy image processing
    
* Customer C → Kubernetes asking “Are you alive?”
    

If the cashier is busy, Customer C waits.

Kubernetes waits 1 second.  
Then 2 seconds.  
Timeout.

Kubernetes assumes the process is dead.

It kills the pod.

Your app wasn’t dead.  
It was just starved.

> This failure pattern is extremely common in async Python services running behind Kubernetes.

# Mistake #1: “Deep” Health Checks

This is the most common failure pattern.

```plaintext
@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    user = db.query(User).first()
    return {"status": "ok"}
```

Looks harmless.

It isn’t.

If your DB pool is exhausted or under pressure:

* `get_db()` waits for a connection
    
* request hangs
    
* health check times out
    
* Kubernetes kills your pod
    

Now your database hiccup becomes a full web server restart.

That’s not health monitoring. That’s self-sabotage.

# The Correct Design: Split Probes

Kubernetes gives you two tools:

### 1- Liveness Probe

**Question:** “Is the process alive?”

It should:

* return instantly
    
* not touch the DB
    
* not call Redis
    
* not do logic
    

```plaintext
@app.get("/health/live")
async def liveness():
    return {"status": "alive"}
```

That’s it.

If this fails, your process is truly frozen.

### 2- Readiness Probe

**Question:** “Can this instance handle traffic right now?”

This is where you check:

* DB connectivity
    
* Redis
    
* downstream services
    

```plaintext
@app.get("/health/ready")
async def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        raise HTTPException(status_code=503)
```

If readiness fails:

* Kubernetes stops routing traffic
    
* Pod stays alive
    
* No restart
    

That’s the correct behavior.

# Mistake #2: Aggressive Probe Settings

![](https://cdn.hashnode.com/res/hashnode/image/upload/v1770796314735/62ca8fae-09ad-4a1d-901a-e3e1ddbd1ad8.png align="center")

Many clusters default to:

* timeoutSeconds: 1
    
* failureThreshold: 3
    

That means:

3 seconds of event loop delay = pod death.

That’s too aggressive for Python.

A safer baseline:

```plaintext
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 5
```

Give your app breathing room.

Python has:

* GC pauses
    
* I/O jitter
    
* occasional event loop delays
    

You don’t want restarts because of micro-stalls.

If your event loop is getting blocked, I broke this down deeply [here](https://www.logiclooptech.dev/why-fastapi-apps-slow-down-over-time-low-cpu-high-latency-explained).

# Mistake #3: Blocking the Event Loop

Even a perfect `/health/live` can fail if something else is blocking the loop.

Common culprits:

* `time.sleep()` inside `async def`
    
* heavy password hashing
    
* large JSON parsing
    
* CPU-bound work
    
* sync HTTP calls (`requests.get`)
    

If the event loop is blocked for 5 seconds, your health check never runs.

The timeout is a symptom.

The disease is blocking code.

![](https://cdn.hashnode.com/res/hashnode/image/upload/v1770796349689/760a9342-96f0-4b4f-8e20-2a43cb7692ad.png align="center")

# Optional Strategy: Use `def` Instead of `async def`

FastAPI runs normal `def` endpoints in a thread pool.

For health endpoints specifically:

```python
@app.get("/health/live")
def liveness():
    return {"status": "alive"}
```

This can sometimes isolate it from event loop stalls.

But if your process is truly saturated, this won’t save you.

It’s a mitigation, not a cure.

Incorrect worker counts can amplify probe failures and [here’s the math](https://www.logiclooptech.dev/how-many-uvicorn-workers-do-you-actually-need-fastapi-performance-guide).

# The Nuclear Option: Separate Health Port

In high-load systems, some teams run health checks on a separate port using a minimal HTTP server.

Why?

Even if Uvicorn is saturated, the OS can still answer on another thread.

This is rare and usually unnecessary, but in extreme environments, it removes probe-related restarts entirely.

## What Causes Liveness Probe Failures in FastAPI?

Most probe failures are not crashes infact they are timeout failures caused by event loop starvation.

# The Real Lesson

When pods restart under load:

It’s usually not a crash.

It’s starvation.

Your application was alive, it was just unable to respond fast enough.

# Final Checklist

✔ Split `/live` and `/ready`  
✔ Keep `/live` dumb and instant  
✔ Don’t put DB logic in liveness  
✔ Increase timeoutSeconds  
✔ Remove blocking code  
✔ Scale workers if needed

Health checks should detect death, they should not cause it.

## Symptoms You’ll Notice Before Pods Restart

* Random pod restarts during traffic spikes
    
* No Python errors
    
* Health endpoint timing out
    
* CPU elevated but not maxed
    
* Latency spikes before restart