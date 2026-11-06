# Cache Test: Lex With vs. Without the Prompt Cache

*Problem 4, part B. Campus Customs is a fictional class setting. All numbers come from `output/cache_test.json`:
48 model calls (12 practice documents × 2 calls × 2 setups), with every token count exactly as the API reported it
and dollars priced from `data/prices.json`.*

**How each setup was built**
- **Cache off:** `python agent.py --doc data/practice_docs --cache off --save-calls output/cache_test.json`
  OpenAI cache mode set to "explicit" with no breakpoints, plus a new random id at the start of every request.
- **Cache on:** `python agent.py --doc data/practice_docs --cache on --save-calls output/cache_test.json`
  The instructions and handbook are identical on every call, plus a `prompt_cache_key`.

---

## 1. Cost per setup

| | Cache OFF | Cache ON |
|---|---|---|
| Model calls | 24 | 24 |
| Input tokens | 265,838 | 265,199 |
| … billed at full price ($0.10/1M) | 265,838 | 3,024 |
| … read from cache ($0.01/1M) | 0 | 249,287 (94%) |
| … written to cache ($0.125/1M) | 0 | 12,888 |
| Output tokens ($0.50/1M) | 2,781 | 2,937 |
| **Total cost (12 documents)** | **$0.027974** | **$0.005875** |
| **Cost per document** | **$0.002331** | **$0.000490** |
| Decisions matching the key | 8/12 | 8/12 |

### Percent saved
```
1 − $0.005875 ÷ $0.027974 = 79.0% saved
```
Once the cache was warm (documents 2–12), each document cost $0.000384, which is **83.5% saved**.

**Proof each setup did what we expected:** with the cache OFF, every one of the 24 calls reported
**0 cached and 0 written**. With the cache ON, 23 of 24 calls read about 10,830 tokens from cache. The only call
that didn't was the very first one, which wrote the cache (10,847 tokens).

🛑 **Adrian:**

---

## 2. Real numbers vs. the Problem 2 estimate

| | Problem 2 estimate | Real (Problem 4) | Why they differ |
|---|---|---|---|
| Input tokens per call | 10,058 (handbook only) | **~11,000** | Each call also carries Lex's instructions, the tool definitions and the answer format, about 940 tokens. |
| Model calls per document | 1 | **2** | Lex calls `read_document` first, then answers. The handbook goes out on **both** calls. |
| Cost per 1,000 docs, no cache | ~$1.13 | **$2.33** | Two calls per document: 2 × ~$1.13 ≈ $2.26, plus output. ✅ It matches once the 2 calls are counted. |
| Cost per 1,000 docs, cached | ~$0.10 (handbook only) | **$0.49** | Two calls, cache writes, and output that is never cached (see section 4). |
| Percent saved | ~90% | **79%** (83.5% warm) | Cache writes and output aren't discounted. |

**Bottom line:** the estimate was right about the handbook. It missed that Lex makes **two** calls per document
and that the extras (instructions, tools, writes, output) add up.

🛑 **Adrian:**

---

## 3. Projection: 1,000 documents a day for 30 days (30,000 documents)

| | Cost per document | 30-day cost |
|---|---|---|
| **Without cache** | $0.002331 | **$69.94** |
| **With cache** (warm all day, plus one cold start per day) | $0.000384 | **$11.57** |
| **Saved** | | **$58.37 a month (83%)** |

```
Without: 30,000 × $0.002331 = $69.94
With:    30,000 × $0.000384 = $11.53  +  30 cold starts × $0.00126 extra = $0.04  →  $11.57
```
At 1,000 documents a day, a new document arrives every minute or two, so the cache stays warm. If the cache went
cold often (say, every 12 documents, like our test), it would be about $14.69 a month, still a 79% saving.

🛑 **Adrian:**

---

## 4. What was not expected, and why

1. **Lex sends the handbook twice per document.** Call 1 asks for the file and call 2 gives the answer, and both
   carry the full system prompt. That doubled the bill compared with the Problem 2 estimate. *Why:* the agent reads
   the document with a tool, which adds a round trip.

2. **The cache also writes things it will never reuse.** On every document, the cache wrote about 20 tokens (the
   request) plus about 150 (the document text), at **$0.125/1M, which is more than the normal $0.10**. Cache writes
   are **27% of the cached bill**. *Why:* the provider automatically caches the end of every prompt, but each vendor
   document only appears once. A fix would be to mark one cache breakpoint right after the handbook, so only the
   handbook gets written.

3. **Output is now a quarter of the bill.** With the cache off, output is 5% of the cost. With it on, it's
   **25%**, because output is never cached and it's billed at 5× the input price.

4. **Hidden "reasoning" tokens.** The API reported 1,488 (off) and 1,629 (on) **reasoning tokens**: the model
   thinking before it answers. They're billed as output, and they're most of call 2's output.

5. **The model name came back as `gpt-6-luna-global`.** That's Portkey's routing name for the same model. Every
   request asks for `gpt-6-luna` (the only model name in our code). Worth one line in the write-up, since points
   are deducted if another model shows up.

6. **The cached amount is about 10,830 tokens, not 10,058.** The part that stays the same on every call is the
   handbook **plus** Lex's instructions, the tool definitions and the answer format.

7. **The first document with cache on still saved money.** Its first call wrote the cache, and its second call
   read it back right away, so even a cold start costs less than no cache ($0.00165 vs. $0.00233).

8. **Same documents, slightly different numbers each run.** Output tokens vary run to run (for example, 151 to 260
   on the same call), so cost moves a little (part A: $0.027955, part B: $0.027974). *Why:* the model's wording
   isn't identical each time.

🛑 **Adrian:**
