"""Re-export of `hoctap.content.arith` (the evaluator moved so `learning` need not import
`builder`)."""

from hoctap.content.arith import MAX_DEPTH, MAX_TOKENS, evaluate, format_number

__all__ = ["MAX_DEPTH", "MAX_TOKENS", "evaluate", "format_number"]
