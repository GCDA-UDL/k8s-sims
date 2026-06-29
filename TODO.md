# TODO

## Deferred — after the experiment/test campaign is complete

- [ ] **Upload datasets + benchmark results to CORA / RDR** (Repositori de Dades
      de Recerca, Dataverse, CSUC). Package: `results-repro/` + the generated
      datasets (Alibaba/Borg/Azure/Philly) + a data README + metadata. Use **CC-BY** for
      data (not Apache). Mint a data DOI and **cross-link it with the software
      DOI** (the forthcoming KubeSBS Zenodo DOI) via related identifiers.
      Deferred on 2026-06-15 by maintainer until the test runs finish.

## Open

- [x] Add **Matias Nicolas Medina Jara**'s ORCID (`0009-0000-2858-4317`) to
      `CITATION.cff` + `.zenodo.json`. (The old published Zenodo record was
      deleted; correct ORCIDs will ship with the KubeSBS re-upload.)
- [ ] Confirm with the FACTOS project / UAB whether any funding acknowledgment
      beyond MICIU `PID2023-146193OB-I00` must be added (shared-project check).
- [ ] **Sample parity:** the Philly `.json` synthetic sample is committed, but the
      borg/azure `.csv` samples under `utils/trace-convert/samples/` are gitignored.
      Force-add them for parity: `git add -f utils/trace-convert/samples/*.csv`.
- [ ] **Philly converter — real-trace + GPU run:** `philly2base.py` is validated on
      the synthetic sample only (5 jobs → 2 GPU nodes, 16 GPUs). Download the real
      `cluster_job_log` (`msr-fiddle/philly-traces`, via `download_traces.sh --philly`)
      and run it through a **GPU-aware scheduler** to actually exercise
      `nvidia.com/gpu`; current sims schedule by cpu/memory, so GPU placement is
      untested. Feeds the GPU-scheduling-fidelity sub-study of paper #3 (C1).

## Done (for reference)

- [ ] ~~Software DOI on Zenodo (concept `10.5281/zenodo.20694295`)~~ — **record
      DELETED 2026-06-29.** Re-release the artifact as **KubeSBS** with a new DOI,
      then update CITATION.cff, README, and .zenodo.json.
