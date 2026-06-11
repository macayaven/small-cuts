# KB note mirrors

The canonical knowledge base (`.knowledge/` + `knowledge_base-*` MCP tools)
lives on the Mac Studio and was **not reachable from the cloud session that
bootstrapped this repo** (no knowledge_base MCP server, no `.knowledge/`
directory, no Tailnet).

These markdown files are faithful, import-ready mirrors of the notes that the
operating contract requires. Each file's front matter carries the intended
`projectId` and `id`.

**Action for the next Mac Studio session:** import each note via
`knowledge_base-knowledge_save` using the front-matter `projectId`/`id`,
then keep the canonical KB as source of truth (mirror here may lag).
