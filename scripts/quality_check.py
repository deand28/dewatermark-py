import sys
sys.path.insert(0, "src")
from dewatermark.rewrite import rewrite

SAMPLE = (
    "The quarterly report shows that revenue grew significantly across all "
    "major segments this year. Infrastructure spending decreased slightly as "
    "the organization shifted priorities toward research and development. "
    "Customer retention improved because support response times were reduced "
    "by nearly half. The board expects continued growth throughout the next "
    "fiscal period, driven primarily by expansion into adjacent markets and "
    "strategic partnerships with established regional distributors."
)

out, backend = rewrite(SAMPLE)
print("BACKEND:", backend)
print("LEN IN:", len(SAMPLE), "LEN OUT:", len(out))
print("---")
print(out)
