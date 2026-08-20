# MCP Creator-CRM Agent — Natural Language GMV Queries

MCP server design, LangChain/Bedrock agentic tool-calling, and API access to affiliate-style data.

**Live demo:** https://reacher.ashanpraba.com

The demo runs entirely in the browser against seeded data — no API keys,
no accounts, and no external services required.

## Stack

- Python
- MCP
- LangChain
- AWS Bedrock
- SQLite (mock CRM data)

## How it works

- A mock SQLite table of ~15 creators with fields: name, status, last_contact, samples_sent, gmv_last_30d.
- Write an MCP server exposing 3 tools: get_creator(name), list_top_by_gmv(n), list_stalled_creators(days).
- A LangChain agent (Bedrock Claude/Titan) to the MCP tools using function/tool-calling.
- Write 3-4 canned natural language questions and run them through the agent in a terminal loop.
- Record terminal output showing the agent's tool calls and final answers for the demo take.

## Running locally

```bash
cd src
bash run.sh
```

Then open the printed URL. A prebuilt static version of the UI lives in
`src/web/` and can be opened directly with no server.
