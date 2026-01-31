---
layout: post
title: Tracking Claude Code Subagent Costs
date: 2026-01-31
---

When using Claude Code's Task tool to spawn subagents, it's easy to lose track of how much you're spending in tokens and money. I'm not really worried about going bankrupt from a combinatorial explosion of sub-agents; it's more that if I've got a dashboard I can have a good mental map of what's going on in the ever expanding empire of agents.

Claude Code can spawn subagents via the Task tool - specialized agents for exploration, research, code execution, etc. These are powerful for delegation, but:

1. **No built-in cost visibility** - You don't see per-subagent token usage
2. **Multiple agents per task** - A single request might spawn several agents
3. **Model varies** - Subagents might use Opus, Sonnet, or Haiku depending on the task

Without tracking, you can't answer: "How much did that research task actually cost?" 

There is a nice tool `ccusage` which displays relevant information on tokens per session but it doesn't seem to track well at the sub-agent level and session level, and doesn't link it to specific tasks that I have sent a sub-agent to do. 

## The Solution

Use Claude Code's hook system to log subagent lifecycle events, then parse the transcript files to extract actual token usage.

### Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  SubagentStart  │────▶│  task-logger.sh  │────▶│ task-starts.jsonl│
│     hook        │     │                  │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘

┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  SubagentStop   │────▶│ task-completion-     │────▶│ task-completions.   │
│     hook        │     │ logger.sh            │     │ jsonl               │
└─────────────────┘     └──────────────────────┘     └─────────────────────┘

┌─────────────────────┐     ┌──────────────────┐
│ Subagent transcript │────▶│ analyze-task-    │────▶ Token counts + costs
│ files (.jsonl)      │     │ tokens.sh        │
└─────────────────────┘     └──────────────────┘
```

## Implementation

### Step 1: Create the Logging Hooks

Create `~/.claude/hooks/task-logger.sh`:

```bash
#!/usr/bin/env bash
# Log subagent start events
set -euo pipefail

INPUT=$(cat)
AGENT_ID=$(echo "$INPUT" | jq -r '.agent_id // empty')
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if [ -n "$AGENT_ID" ]; then
  LOG_DIR="$HOME/path/to/your/logs"  # Customize this
  mkdir -p "$LOG_DIR"
  echo "$INPUT" | jq -c ". + {logged_at: \"$TIMESTAMP\"}" >> "$LOG_DIR/task-starts.jsonl"
fi

exit 0
```

Create `~/.claude/hooks/task-completion-logger.sh`:

```bash
#!/usr/bin/env bash
# Log subagent completion events with transcript metrics and task description
set -euo pipefail

INPUT=$(cat)
AGENT_ID=$(echo "$INPUT" | jq -r '.agent_id // empty')
AGENT_TRANSCRIPT=$(echo "$INPUT" | jq -r '.agent_transcript_path // empty')
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if [ -n "$AGENT_ID" ]; then
  LOG_DIR="$HOME/path/to/your/logs"  # Customize this
  mkdir -p "$LOG_DIR"

  # Extract transcript metrics and task description
  if [ -n "$AGENT_TRANSCRIPT" ] && [ -f "$AGENT_TRANSCRIPT" ]; then
    TRANSCRIPT_LINES=$(wc -l < "$AGENT_TRANSCRIPT" | tr -d ' ')
    TRANSCRIPT_SIZE=$(stat -f%z "$AGENT_TRANSCRIPT" 2>/dev/null || stat -c%s "$AGENT_TRANSCRIPT" 2>/dev/null || echo "0")
    # Extract first 100 chars of task prompt from first message
    TASK_DESC=$(head -1 "$AGENT_TRANSCRIPT" | jq -r '.message.content // empty' 2>/dev/null | head -c 100 | tr '\n' ' ')
  else
    TRANSCRIPT_LINES=0
    TRANSCRIPT_SIZE=0
    TASK_DESC=""
  fi

  echo "$INPUT" | jq -c --arg desc "$TASK_DESC" ". + {logged_at: \"$TIMESTAMP\", transcript_lines: $TRANSCRIPT_LINES, transcript_bytes: $TRANSCRIPT_SIZE, task_description: \$desc}" >> "$LOG_DIR/task-completions.jsonl"
fi

exit 0
```

Make them executable:
```bash
chmod +x ~/.claude/hooks/task-logger.sh
chmod +x ~/.claude/hooks/task-completion-logger.sh
```

### Step 2: Register the Hooks

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$HOME/.claude/hooks/task-logger.sh\""
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$HOME/.claude/hooks/task-completion-logger.sh\""
          }
        ]
      }
    ]
  }
}
```

### Step 3: Create the Analysis Script

Create `analyze-task-tokens.sh`:

```bash
#!/usr/bin/env bash
# Analyze token usage for subagent tasks
set -euo pipefail

LOG_DIR="$HOME/path/to/your/logs"  # Customize this
STARTS_LOG="$LOG_DIR/task-starts.jsonl"
COMPLETIONS_LOG="$LOG_DIR/task-completions.jsonl"

# Pricing per million tokens (as of Jan 2026 - update as needed)
OPUS_INPUT=15; OPUS_OUTPUT=75; OPUS_CACHE_WRITE=18.75; OPUS_CACHE_READ=1.50
SONNET_INPUT=3; SONNET_OUTPUT=15; SONNET_CACHE_WRITE=3.75; SONNET_CACHE_READ=0.30
HAIKU_INPUT=0.80; HAIKU_OUTPUT=4; HAIKU_CACHE_WRITE=1.00; HAIKU_CACHE_READ=0.08

extract_tokens() {
  local transcript_path="$1"
  [ ! -f "$transcript_path" ] && echo '{"input":0,"output":0,"cache_write":0,"cache_read":0,"model":"unknown"}' && return

  jq -s '
    map(select(.message.usage != null) | .message) |
    {
      model: (.[0].model // "unknown"),
      input: (map(.usage.input_tokens // 0) | add),
      output: (map(.usage.output_tokens // 0) | add),
      cache_write: (map(.usage.cache_creation_input_tokens // 0) | add),
      cache_read: (map(.usage.cache_read_input_tokens // 0) | add)
    }
  ' "$transcript_path" 2>/dev/null || echo '{"input":0,"output":0,"cache_write":0,"cache_read":0,"model":"unknown"}'
}

calculate_cost() {
  local model="$1" input="$2" output="$3" cache_write="$4" cache_read="$5"
  local ip op cwp crp

  if [[ "$model" == *"opus"* ]]; then
    ip=$OPUS_INPUT; op=$OPUS_OUTPUT; cwp=$OPUS_CACHE_WRITE; crp=$OPUS_CACHE_READ
  elif [[ "$model" == *"sonnet"* ]]; then
    ip=$SONNET_INPUT; op=$SONNET_OUTPUT; cwp=$SONNET_CACHE_WRITE; crp=$SONNET_CACHE_READ
  else  # Default to Haiku
    ip=$HAIKU_INPUT; op=$HAIKU_OUTPUT; cwp=$HAIKU_CACHE_WRITE; crp=$HAIKU_CACHE_READ
  fi

  echo "scale=4; ($input * $ip + $output * $op + $cache_write * $cwp + $cache_read * $crp) / 1000000" | bc
}

show_tokens() {
  local n=${1:-5}
  [ ! -f "$COMPLETIONS_LOG" ] && echo "No logs yet." && return

  echo "Token usage for last $n tasks:"
  echo ""

  local types_json="{}"
  [ -f "$STARTS_LOG" ] && types_json=$(jq -s 'map({(.agent_id): .agent_type}) | add // {}' "$STARTS_LOG")

  tail -n "$n" "$COMPLETIONS_LOG" | while read -r line; do
    local agent_id=$(echo "$line" | jq -r '.agent_id')
    local transcript_path=$(echo "$line" | jq -r '.agent_transcript_path // empty')
    local logged_at=$(echo "$line" | jq -r '.logged_at')
    local task_desc=$(echo "$line" | jq -r '.task_description // empty')
    local agent_type=$(echo "$types_json" | jq -r --arg id "$agent_id" '.[$id] // "unknown"')

    echo "Agent: $agent_type ($agent_id)"
    [ -n "$task_desc" ] && echo "  Task: ${task_desc:0:80}..."
    echo "  Completed: $logged_at"

    if [ -n "$transcript_path" ] && [ -f "$transcript_path" ]; then
      local tokens=$(extract_tokens "$transcript_path")
      local model=$(echo "$tokens" | jq -r '.model')
      local input=$(echo "$tokens" | jq -r '.input')
      local output=$(echo "$tokens" | jq -r '.output')
      local cache_write=$(echo "$tokens" | jq -r '.cache_write')
      local cache_read=$(echo "$tokens" | jq -r '.cache_read')
      local cost=$(calculate_cost "$model" "$input" "$output" "$cache_write" "$cache_read")

      echo "  Model: $model"
      echo "  Tokens: $input in, $output out, $cache_write cache write, $cache_read cache read"
      printf "  Cost: \$%.4f\n" "$cost"
    else
      echo "  (No transcript found)"
    fi
    echo ""
  done
}

case "${1:-}" in
  --help|-h) echo "Usage: $0 [--tokens [n]]" ;;
  --tokens) show_tokens "${2:-5}" ;;
  *) show_tokens 5 ;;
esac
```

## Usage

After setup, subagent usage is automatically logged. View costs with:

```bash
# See last 5 tasks with token usage
./analyze-task-tokens.sh --tokens

# See last 10 tasks
./analyze-task-tokens.sh --tokens 10
```

Example output:

```
Token usage for last 3 tasks:

Agent: Explore (a1b2c3d)
  Task: Research helmet options for commuting. Look for folding helmets and...
  Completed: 2026-01-31T18:13:32Z
  Model: claude-haiku-4-5-20251001
  Tokens: 3 in, 1 out, 14321 cache write, 0 cache read
  Cost: $0.0143

Agent: web-researcher (e4f5g6h)
  Task: Find reviews and pricing for Raleigh Denim jeans. Compare fits and sizing...
  Completed: 2026-01-31T18:25:39Z
  Model: claude-sonnet-4-20250514
  Tokens: 5200 in, 1800 out, 0 cache write, 12000 cache read
  Cost: $0.0456

Agent: general-purpose (a3d3c72)
  Task: Build invite pool for a recurring event from Partiful CSV cross-referenced with...
  Completed: 2026-01-31T19:04:24Z
  Model: claude-haiku-4-5-20251001
  Tokens: 3 in, 1 out, 23518 cache write, 0 cache read
  Cost: $0.0235
```

Now I can see exactly what each subagent was tasked with, making it easy to correlate costs with specific delegated work. (Note this works because I also have a task set up with task IDs linked in my Obsidian )

 My guess is that I'm not going to learn all that much specifically, but that the system-two level feedback will train my system-one to be more willing to delegate tasks,  and that it will help me manage larger more expensive delegation tasks as that becomes more possible 

## Extensions

Ideas for building on this:

- **Aggregate by session** - Sum all subagent costs for a given parent session
- **Daily summaries** - Cron job to email daily subagent spend
- **Cost alerts** - Warn if a single task exceeds threshold
- **Dashboard** - Build a simple web UI to visualize spending over time
