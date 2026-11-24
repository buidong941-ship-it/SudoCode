# Manual clarification review examples

For H13-048 and equivalent cases, a passing phrase must identify the unresolved product reference:

- Valid: ?Ch? cho em xin t?n m?u c? th? ?? em ki?m tra ??ng m?y ?.?
- Invalid despite containing an accepted keyword: ?M?u n?o c?ng ???c, ch? c? ch?t ?i.? This does not resolve which product the customer meant and must not authorize `order.create`.

The BTC `must_say_any` field checks substrings only. Review the actual assistant utterance and tool calls; do not treat lexical matching as a semantic pass.
