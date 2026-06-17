"""Trace the planner on one prompt: show the outline, then each IR attempt's
raw output and validation error. Use to diagnose mock-fallbacks."""

import json
import sys

from pydantic import ValidationError

from assets import catalog
from ir import Scene
from planner import IR_SYSTEM, _chat, _coerce, _strip_to_json, pick_model, plan_outline

prompt = " ".join(sys.argv[1:]) or "a circle moving across the board"
model = pick_model()
print(f"model={model}\nprompt={prompt!r}\n")

outline = plan_outline(prompt, model)
print("OUTLINE:", json.dumps(outline, indent=2), "\n")

system = IR_SYSTEM.replace("__CATALOG__", catalog())
messages = [
    {"role": "system", "content": system},
    {"role": "user", "content": f"Topic: {prompt}\n\nOutline:\n{json.dumps(outline)}"},
]
for i in range(3):
    raw = _chat(model, messages)
    print(f"--- attempt {i} raw ---\n{raw[:1500]}\n")
    try:
        Scene.model_validate(_coerce(json.loads(_strip_to_json(raw))))
        print(f"attempt {i}: VALID")
        break
    except (json.JSONDecodeError, ValidationError) as e:
        print(f"attempt {i} ERROR: {e}\n")
        messages.append({"role": "assistant", "content": raw})
        messages.append(
            {
                "role": "user",
                "content": f"That JSON was invalid:\n{e}\nFix ALL of these errors and return the full corrected Scene IR JSON only.",
            }
        )
