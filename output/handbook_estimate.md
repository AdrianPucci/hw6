# Handbook Cost Estimate

*Problem 2: Size Up the Handbook. Campus Customs is a fictional class setting.*
*The full study guide is `Handbook Cost Analysis.docx`.*

---

## 1. How many tokens is the handbook?

**10,058 tokens.** This was measured, not guessed: I sent the handbook to gpt-6-luna and read back the input token count from the response (`usage.prompt_tokens`), then subtracted a near-empty baseline call to remove the fixed overhead.

```
Handbook call   − baseline call  + 1 ("x")  = 10,058 tokens
```

The quick rule of thumb (characters ÷ 4) gives 28,903 ÷ 4 ≈ 7,200, which is **28% too low**. The handbook's tables of SKUs and prices pack in about **2.9 characters per token**, not 4.

🛑 **Adrian:** Ran comparison. Evaluated outcomes. Not there yet. 

---

## 2. The one formula

```
cost = tokens × price per 1M ÷ 1,000,000
```

Prices from `data/prices.json` (gpt-6-luna, per 1M tokens): **input $0.10 · cached input $0.01 · cache write $0.125 · output $0.50**

🛑 **Adrian:** Evaluating the formula 

---

## 3. The calculations

**One call (full handbook, normal input)**
```
10,058 × $0.10 ÷ 1,000,000 = $0.0010058   ≈ 1/10 of a cent
```

**1,000 calls**
```
$0.0010058 × 1,000 = $1.01
```

**1,000 calls with caching** (the first call writes the cache, the other 999 read it)
```
write:  10,058 × $0.125 ÷ 1,000,000         = $0.00126
reads:  10,058 × $0.01  ÷ 1,000,000 × 999   = $0.10048
total                                       ≈ $0.10   (90% less)
```

**1,000 calls trimmed** (rules sections 4, 5, 6 and 13 plus one catalogue row, measured at 1,024 tokens)
```
1,024 × $0.10 ÷ 1,000,000 × 1,000 = $0.10   (90% less)
```

🛑 **Adrian:** looking at an alternative to dial in how the process works.

---

## 4. Brief explanation

- **The catalogue (section 9) is 64% of the handbook** (6,447 of 10,058 tokens), but each quote needs only one row of it.
- **Two ways to cut the bill:** cache the handbook (it gets cheaper to re-read) or trim it (send fewer tokens). Both save about 90%.
- **These numbers count the handbook only.** Real calls also carry the vendor document, the instructions and the answer, so the prediction for **Problem 4** is about **$1.13 per 1,000 calls** with the full handbook and about **$0.22** trimmed.

🛑 **Adrian:**

Final formula for our math: 

```
cost = tokens × price per 1M ÷ 1,000,000
10,058 × $0.10 ÷ 1,000,000 = $0.0010058 per call
$0.0010058 × 1,000 = $1.01 per 1,000 calls
```

---

## My comments

🛑 **Adrian:** We're keeping the full handbook and letting caching cut the cost (**scenario A, cached: 10,058 tokens, $0.10 per 1,000 calls, 90% saved**). That avoids the risks of trimming, so we don't need extra guardrails.
