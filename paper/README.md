# Paper source

`main.tex` is the standalone IEEE conference manuscript associated with this
artifact. Build it from the repository root with:

```bash
make paper
```

The command runs pdfLaTeX and BibTeX in the required sequence. Build products
are ignored by Git.

Experiment scripts generate provisional tables under `paper/generated/`.
Confirmatory paper values should be copied only from a complete Nibi run
after `jobs/nibi/aggregate.sh` has validated every expected shard and written
the aggregate checksums.
