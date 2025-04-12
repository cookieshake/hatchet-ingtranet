from hatching import hatchet
from hatching.workflows.nriy_v1 import wf

worker = hatchet.worker("nriy", workflows=[wf])

