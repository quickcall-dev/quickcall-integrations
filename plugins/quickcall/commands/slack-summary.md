---
description: Summarize Slack messages. Usage: /quickcall:slack-summary 7d (for 7 days)
---

# Slack Message Summary

Summarize recent Slack messages from selected channels.

## Arguments

Parse `$ARGUMENTS` for time period:
- `7d` → 7 days
- `3d` → 3 days
- No argument → default to 1 day

## Instructions

1. **First, list available channels:**
   - Use `list_slack_channels` tool to get channels the bot has access to
   - Filter to only show channels where `is_member` is true

2. **Ask user which channels to summarize:**
   - Present a numbered list of channels (show name and whether private)
   - Ask user to select channels (comma-separated numbers or "all")
   - Example: "Which channels would you like to summarize? (1,2,3 or 'all')"

3. **For each selected channel:**
   - Use `read_slack_messages` tool with the parsed days and channel name
   - Thread replies are automatically included

4. **Summarize the messages:**
   - Group by channel
   - For each channel, provide:
     - Key discussions/topics
     - Important decisions or action items
     - Questions that were asked (and answers if available)
     - Notable announcements
   - Keep it concise - bullet points preferred

## Output Format

```
## Slack Summary (last {N} days)

### #channel-name
- **Topic 1:** Brief summary of discussion
- **Decision:** Any decisions made
- **Action items:** Tasks mentioned
- **Questions:** Open questions or Q&A

### #another-channel
...

---
*{total_messages} messages summarized from {num_channels} channels*
```
