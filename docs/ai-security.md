# AI and tool security

The local LLM is an untrusted decision-support component. It can classify a
request or propose one bounded action, but it never supplies identity,
authorization, SQL, Python symbols, filesystem paths, URLs, or executable
commands. The authenticated FastAPI dependency supplies `user_id` and remains
the authority.

## Action flow

```text
authenticated request
  -> bounded intent proposal
  -> strict JSON parsing
  -> Pydantic discriminated action validation
  -> server-owned allowlist/registry
  -> owned-object query using authenticated user_id
  -> one bounded database mutation
```

`backend/app/services/ai_actions.py` contains the action contracts and
registry. Unknown action names, extra fields, ownership fields, invalid enums,
invalid dates, invalid time zones, oversized strings, and malformed JSON are
rejected. The registry has no dynamic imports or model-selected callables.

Supported actions are task create/update/complete/delete, reminder
create/cancel, the explicitly limited username setting update, document search,
and document summarization proposals. Destructive task deletion and reminder
cancellation require explicit confirmation in the user message. Cross-user
object identifiers are rejected by owner-scoped queries.

## Prompt-injection model

User messages, task data, chat history, profile names, filenames, and retrieved
documents are untrusted data. Prompts mark these regions explicitly and tell
the model not to treat their contents as policy or tool instructions. Stored
history cannot change identity, tools, ownership, or system rules. Prompt text
is defense-in-depth only; executable authority is enforced by the typed action
and database boundary.

## RAG and resources

RAG access is `authenticated user -> SQL/document ownership -> server-supplied
Chroma user_id filter -> bounded retrieved text`. The LLM cannot choose the
filter. Retrieval is capped at ten chunks and twelve thousand characters for
prompt construction. No AI path performs arbitrary HTTP requests, shell
commands, raw SQL, dynamic imports, or arbitrary file opens.

Model output is limited to one action proposal per turn, bounded JSON and
bounded action fields. Malformed output, model failure, unauthorized IDs,
tool exceptions, or invalid values produce no action and no success claim.
Errors returned to clients are generic; detailed failures remain in server
logs. Access tokens and configuration secrets are never placed in prompts.

## Known limitations

The existing local model and scheduler remain process-local, and the general
assistant can still produce free-form conversational text. This phase does not
redesign RAG, scheduling, reminder delivery, or authentication. Future work
should add stronger confirmation state and integration tests around every
natural-language action path before enabling broad automation.
