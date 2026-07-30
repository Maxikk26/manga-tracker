# Telegram Digest Specification

## Purpose

The digest emitter — message 1 of three, the only message type in scope for this phase (spec-bot-telegram.md §"Mensaje 1"). Heartbeat and the dead-slug notice are explicitly out of scope.

## Requirements

### Requirement: No DB or source knowledge

The bot MUST receive already-resolved structured data from discovery (title, new chapter number, my progress, accumulation, candidate URLs) and MUST NOT query the database or know the source's URL pattern (spec-bot-telegram.md §"Qué recibe y qué no").

#### Scenario: Bot never queries the DB

- GIVEN discovery calls the digest emitter with a list of novelties
- WHEN the emitter builds the message
- THEN it uses only the data passed in, issuing no database query

### Requirement: Startup token/chat validation

The process MUST fail fast at startup if the Telegram bot token or chat id environment variable is missing, logging a clear message before any digest send is attempted (spec-bot-telegram.md §"Configuración y token").

#### Scenario: Missing token halts startup

- GIVEN the bot token environment variable is unset
- WHEN the process starts
- THEN it fails immediately with a clear log message, before scheduling any job

### Requirement: Manual test-send utility

A manually invoked mode MUST exist that sends a verification message to the configured chat, used at deploy time and after token rotation; it MUST NOT run automatically (spec-bot-telegram.md §"Configuración y token").

#### Scenario: Test-send only runs on demand

- GIVEN the operator invokes the test-send mode
- WHEN it runs
- THEN one verification message is sent, and no such message is sent on ordinary process start

### Requirement: Digest formatting

The digest MUST use HTML formatting (not Markdown), list one manga per line separated by a blank line, order lines alphabetically by title, show chapter numbers as-is including decimals, omit "vas por el" and link to the newest chapter when progress is null, and truncate an overlong title with an ellipsis (spec-bot-telegram.md §"Mensaje 1").

#### Scenario: Null progress links to newest chapter

- GIVEN a manga's `last_chapter_read` is null
- WHEN its digest line is built
- THEN the "vas por el" clause is omitted and the link targets the newest chapter

### Requirement: Link previews are suppressed

Every outgoing digest message MUST disable link previews. With several linked lines a message full of previews is unreadable on a phone, which is the screen this format is designed for (spec-bot-telegram.md v1.1 §"Resolución del enlace": "La vista previa de enlaces se desactiva en el mensaje").

#### Scenario: A multi-line digest sends with previews off

- GIVEN a digest containing two or more linked manga lines
- WHEN the message is sent
- THEN link previews are disabled on every part of the message, including each part of a size-split send

### Requirement: Link resolution hierarchy

The link for each digest line MUST be resolved in this order, taking the first that applies: (1) the real URL of the first unread chapter from `chapter_history` if registered; (2) the pattern-built URL from the source client's URL-construction operation; (3) the URL of the newest chapter (spec-bot-telegram.md §"Resolución del enlace").

#### Scenario: Real URL preferred

- GIVEN the first unread chapter is already registered in `chapter_history` with a URL
- WHEN the link is resolved
- THEN that real URL is used

#### Scenario: Falls back to pattern-built URL

- GIVEN the first unread chapter has no registered URL but a slug and number are known
- WHEN the link is resolved
- THEN the pattern-built URL is used

#### Scenario: Falls back to newest chapter URL

- GIVEN neither a registered nor a pattern-buildable URL exists
- WHEN the link is resolved
- THEN the newest chapter's URL is used

### Requirement: Size split is all-or-nothing

If the digest exceeds Telegram's message-size limit, it MUST split into multiple messages without cutting a manga's line across messages, and the send MUST count as successful only if every part sent; any part failing MUST make the whole send fail (spec-bot-telegram.md §"Mensaje 1", "Tamaño").

#### Scenario: One part fails, whole send fails

- GIVEN a digest splits into 3 parts and part 2 fails to send
- WHEN discovery evaluates the result
- THEN the send is reported as failed, even though parts 1 and 3 succeeded

### Requirement: Send retry and rate limits

On a rate-limit response, the emitter MUST wait the indicated time and retry once; on any other failure, it MUST retry once after a brief wait, then report failure to discovery if the retry also fails (spec-bot-telegram.md §"Manejo de fallos de envío").

#### Scenario: Rate limit respected

- GIVEN Telegram responds asking to wait N seconds
- WHEN the emitter retries
- THEN it waits N seconds before the single retry

### Requirement: No message with no novelty

No message MUST be sent when a run closes with zero active-manga novelties (spec-bot-telegram.md §"Mensaje 1", "Cuándo").

#### Scenario: Silent run

- GIVEN `feed_check` finds no new chapters for active mangas
- WHEN the run closes
- THEN no Telegram message is sent

## Out of scope this phase

Heartbeat (message 2) and the dead-slug notice (message 3) are not built in this phase (spec-bot-telegram.md §"Mensaje 2", "Mensaje 3"; v1a-heart-phase proposal "Scope — out").

## References

- spec-bot-telegram.md v1.1
