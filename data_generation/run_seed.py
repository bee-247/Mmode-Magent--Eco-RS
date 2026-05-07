from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data_generation.llm_data_generator import LLMDataGenerator
from data_generation.vector_seed_pipeline import VectorSeedPipeline


async def main() -> None:
    products, users = await LLMDataGenerator().generate()
    result = await VectorSeedPipeline().run(products, users)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
