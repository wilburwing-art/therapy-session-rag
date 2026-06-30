# personal-rag feeder

Registers therapy-session-rag as a feeder into the one personal RAG fabric (the
shared Khoj at http://localhost:42110), so its transcripts are queryable
alongside every other personal corpus.

`feed.yaml` declares the source per the rag feed v1 contract. TODO: wire the
sync (transcripts live in the app database, so add an export path first, then
let the hub `sync.py` register it).
