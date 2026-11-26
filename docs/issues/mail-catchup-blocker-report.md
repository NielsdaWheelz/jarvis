# a mail catch-up can park before publishing its partial report

a read-only catch-up can exhaust its available reads and still have a useful result for the owner. when an outstanding read needs consent or the provider withholds the result, the owner needs the verified coverage and the reason for the gap.

reproduce with one proved read and one consent challenge. return a partial answer with `continue` and no future quota deadline. `commit_product` rejects that disposition and the owner receives a protocol-failure notice without the coverage report.

close when the owner receives one private report that distinguishes verified reads, consent challenges and withheld results. keep unverified originals unresolved until new evidence or an explicit owner disposition. verify that restart preserves the report and original effects, and that a future quota deadline still schedules a quiet wait. [recovery contract](../decisions/0114-automatic-foreground-recovery.md)
