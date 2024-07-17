import hnswlib
import numpy as np

index = hnswlib.Index(space="l2", dim=1024)
index.init_index(max_elements=1000, ef_construction=100, M=16)
vectors = np.random.randn(1000, 1024).astype(np.float32)
index.add_items(vectors,ids=np.arange(1000))
print('finished')