-- Sliding-window rate limit for one email. Runs atomically inside Redis, so simultaneous
-- attempts can't both see "4 so far" and both get through.
--
-- KEYS[1]  ratelimit:<email>   a sorted set of attempt times (ms)
-- ARGV[1]  window in ms        ARGV[2]  limit        ARGV[3]  unique id for this attempt
--
-- Returns -1 when the attempt is recorded (allowed), otherwise the ms until the oldest
-- attempt in the window expires (rejected attempts aren't recorded).

local t = redis.call('TIME')  -- Redis's clock, the same for every API worker
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local window = tonumber(ARGV[1])

redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then
  local oldest = tonumber(redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')[2])
  return oldest + window - now
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], window)
return -1
