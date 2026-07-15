"""Lightweight metrics for extraction. Used by benchmark and monitoring."""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class ExtractionMetrics:
    documents_processed: int = 0
    pages_processed: int = 0
    pages_pymupdf: int = 0
    pages_mineru: int = 0
    fallback_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    quality_scores: List[float] = field(default_factory=list)
    times_pymupdf: List[float] = field(default_factory=list)
    times_mineru: List[float] = field(default_factory=list)

    def record_document(self, doc, elapsed: float, used_cache: bool = False):
        self.documents_processed += 1
        n = len(doc.pages)
        self.pages_processed += n
        src = getattr(doc, "source", "")
        if "cache" in src:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

        if "pymupdf" in src and "mixed" not in src:
            self.pages_pymupdf += n
            self.times_pymupdf.append(elapsed)
        elif "mineru" in src or "mixed" in src:
            self.pages_mineru += n
            self.times_mineru.append(elapsed)
            if "mixed" in src or "mineru" in src:
                self.fallback_count += 1

        if hasattr(doc, "metadata") and "page_provenance" in doc.metadata:
            for p in doc.metadata["page_provenance"]:
                if p.get("quality") is not None:
                    self.quality_scores.append(p["quality"])

    def avg_quality(self) -> float:
        return sum(self.quality_scores) / len(self.quality_scores) if self.quality_scores else 0.0

    def avg_time_pymupdf(self) -> float:
        return sum(self.times_pymupdf) / len(self.times_pymupdf) if self.times_pymupdf else 0.0

    def avg_time_mineru(self) -> float:
        return sum(self.times_mineru) / len(self.times_mineru) if self.times_mineru else 0.0

    def snapshot(self) -> Dict[str, Any]:
        return {
            "documents_processed": self.documents_processed,
            "pages_processed": self.pages_processed,
            "pages_pymupdf": self.pages_pymupdf,
            "pages_mineru": self.pages_mineru,
            "fallback_count": self.fallback_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "avg_quality": round(self.avg_quality(), 3),
            "avg_time_pymupdf": round(self.avg_time_pymupdf(), 3),
            "avg_time_mineru": round(self.avg_time_mineru(), 3),
            "hit_rate": round(self.cache_hits / (self.cache_hits + self.cache_misses), 3) if (self.cache_hits + self.cache_misses) > 0 else 0,
        }


METRICS = ExtractionMetrics()


def get_metrics() -> ExtractionMetrics:
    return METRICS


def reset_metrics():
    global METRICS
    METRICS = ExtractionMetrics()