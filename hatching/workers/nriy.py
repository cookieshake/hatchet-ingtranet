from hatching import hatchet
from hatching.workflows.nriy_v1 import wf as nriy_v1
from hatching.workflows.nriy_router import wf as nriy_router

worker = hatchet.worker("nriy", workflows=[nriy_v1, nriy_router])

