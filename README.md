Straight-as-nails mcp server/client for local ollama; starting tool should be GhidraMCP, for instructions on installing look @https://github.com/LaurieWired/GhidraMCP.

## 1. Dependencies.

### installing dependency manager through pip
`pip install poetry`
### installing dependencies through dependencies manager
`poetry install --no-root .`
`poetry shell` (activates venv)

##2. Using mcp client (inside activated venv):

a) Mcp client can be launched in free-chat mode like:
`python mcp_client.py my/path/to/bridge_mcp_ghidra.py` # add any other mcp tools as required (look @error docstring);

It can use all tools as requested as long at it fits inside context (defaults are rather big aimed @24Gb VRam).

b) Mcp client/s can be launched in agent-mode 
`python ghidra_miracle.py my/path/bridge_mcp_ghidra.py`

It is aimed to apply some of the tools for potato-brained (by this I mean boring and time-consuming, no insult to actual potato-brain owners like myself) RE tasks sequentially until user is satisfied (for now it tries to rename variables, list ascii-readable string constants and shoould rename functions based on its functionality (but doesn't work yet), but potentialy it's extendable to any number of tasks (some of which may be implemented in parallel as long as you have enough VRAM), if you can find the right system prompt, that's it;
