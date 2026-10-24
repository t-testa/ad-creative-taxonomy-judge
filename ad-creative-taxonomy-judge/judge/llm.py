"""Optional LLM fallback for names the rules could not decode.

The model is asked to map a name onto the brand's allowed values and return
JSON. Its answer is never trusted as is: every value must be one of the
brand's canonical values, required fields must be present, and the model
can say "unknown". Anything else is rejected and the ad goes to review.
Accepted answers are marked source="llm" so a person can spot-check them.
"""
import json
import os

from .taxonomy import Brand, Parse

MODEL = "claude-sonnet-4-5"


def build_prompt(name: str, brand: Brand) -> str:
    lines = [f"You classify ad names for the brand {brand.name}.",
             "Map the ad name onto the brand's taxonomy. Use only the allowed values below.",
             'If a field cannot be determined from the name, use "unknown". Do not guess.', ""]
    for fld, vals in brand.fields.items():
        lines.append(f"{fld}: {', '.join(vals)}  (team spellings: "
                     + "; ".join(f"{k} = {', '.join(map(str, v))}" for k, v in vals.items()) + ")")
    lines += ["", f"Ad name: {name}", "",
              "Return only JSON with one key per field, for example "
              + json.dumps({f: next(iter(v)) for f, v in brand.fields.items()})]
    return "\n".join(lines)


def validate(raw: str, brand: Brand) -> Parse:
    """Check a model answer against the taxonomy. Returns AUTO-like LLM parse or REVIEW."""
    try:
        data = json.loads(raw.strip().removeprefix("```json").removesuffix("```"))
    except (json.JSONDecodeError, AttributeError):
        return Parse({}, 0.0, "REVIEW", "LLM returned invalid JSON", "llm")
    values, invented = {}, []
    for fld, val in data.items():
        if fld not in brand.fields or val == "unknown":
            continue
        if val in brand.allowed(fld):
            values[fld] = val
        else:
            invented.append(f"{fld}={val}")
    if invented:
        return Parse(values, 0.0, "REVIEW", f"LLM proposed values outside the taxonomy: {', '.join(invented)}", "llm")
    missing = [f for f in brand.required if f not in values]
    if missing:
        return Parse(values, 0.0, "REVIEW", f"LLM could not determine {', '.join(missing)}", "llm")
    return Parse(values, 0.7, "LLM", "decoded by LLM, validated against taxonomy; spot-check", "llm")


def make_client():
    """Return a callable name->raw JSON, or None when no API key is set."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic
    client = anthropic.Anthropic()

    def call(prompt: str) -> str:
        msg = client.messages.create(model=MODEL, max_tokens=200, temperature=0,
                                     messages=[{"role": "user", "content": prompt}])
        return msg.content[0].text
    return call
