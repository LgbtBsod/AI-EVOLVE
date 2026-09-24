"""L8 Probe Frame Clustering - Deduplicate similar frames

Uses perceptual hashing to cluster visually similar frames.
Returns only representative frames to reduce token usage.
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class Cluster:
    """A cluster of visually similar frames"""
    cluster_id: int
    representative_hash: str
    frame_ids: List[int]
    timestamps: List[float]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'cluster_id': self.cluster_id,
            'representative_hash': self.representative_hash,
            'frame_count': len(self.frame_ids),
            'first_frame': self.frame_ids[0],
            'last_frame': self.frame_ids[-1],
            'first_timestamp': self.timestamps[0],
            'last_timestamp': self.timestamps[-1],
            'duration_seconds': self.timestamps[-1] - self.timestamps[0] if len(self.timestamps) > 1 else 0,
        }


class FrameClusterer:
    """Cluster frames by visual similarity using perceptual hashes"""
    
    def __init__(self, max_clusters: int = 10, hamming_threshold: int = 8):
        """
        Initialize clusterer.
        
        Args:
            max_clusters: Maximum number of clusters to keep
            hamming_threshold: Max Hamming distance to consider frames similar
        """
        self.max_clusters = max_clusters
        self.hamming_threshold = hamming_threshold
        self._clusters: List[Cluster] = []
        self._hash_to_cluster: Dict[str, int] = {}
    
    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """Compute Hamming distance between two hex hashes"""
        if len(hash1) != len(hash2):
            return 256  # Max distance for different-length hashes
        
        distance = 0
        for c1, c2 in zip(hash1, hash2):
            try:
                xor = int(c1, 16) ^ int(c2, 16)
                distance += bin(xor).count('1')
            except ValueError:
                return 256
        
        return distance
    
    def add_frame(self, frame_id: int, timestamp: float, perceptual_hash: str) -> Optional[int]:
        """
        Add a frame to clustering.
        
        Args:
            frame_id: Sequential frame number
            timestamp: Unix timestamp
            perceptual_hash: Hex perceptual hash from Rust analyzer
            
        Returns:
            Cluster ID if added to existing cluster, None if new cluster or skipped
        """
        if not perceptual_hash:
            return None
        
        # Check if this hash exactly matches an existing one
        if perceptual_hash in self._hash_to_cluster:
            cluster_id = self._hash_to_cluster[perceptual_hash]
            self._clusters[cluster_id].frame_ids.append(frame_id)
            self._clusters[cluster_id].timestamps.append(timestamp)
            return cluster_id
        
        # Find closest cluster within threshold
        best_cluster_id = None
        best_distance = self.hamming_threshold + 1
        
        for cluster_id, cluster in enumerate(self._clusters):
            distance = self.hamming_distance(perceptual_hash, cluster.representative_hash)
            if distance < best_distance:
                best_distance = distance
                best_cluster_id = cluster_id
        
        # Add to existing cluster if similar enough
        if best_cluster_id is not None:
            self._clusters[best_cluster_id].frame_ids.append(frame_id)
            self._clusters[best_cluster_id].timestamps.append(timestamp)
            self._hash_to_cluster[perceptual_hash] = best_cluster_id
            logger.debug(f"Frame {frame_id} added to cluster {best_cluster_id} (distance={best_distance})")
            return best_cluster_id
        
        # Create new cluster
        new_cluster_id = len(self._clusters)
        new_cluster = Cluster(
            cluster_id=new_cluster_id,
            representative_hash=perceptual_hash,
            frame_ids=[frame_id],
            timestamps=[timestamp],
        )
        self._clusters.append(new_cluster)
        self._hash_to_cluster[perceptual_hash] = new_cluster_id
        logger.debug(f"Created new cluster {new_cluster_id} for frame {frame_id}")
        
        # Enforce max clusters limit
        if len(self._clusters) > self.max_clusters:
            self._merge_smallest_clusters()
        
        return new_cluster_id
    
    def _merge_smallest_clusters(self):
        """Merge the two smallest clusters when limit exceeded"""
        if len(self._clusters) < 2:
            return
        
        # Sort by size (smallest first)
        sorted_clusters = sorted(
            enumerate(self._clusters),
            key=lambda x: len(x[1].frame_ids)
        )
        
        # Merge two smallest
        idx1, cluster1 = sorted_clusters[0]
        idx2, cluster2 = sorted_clusters[1]
        
        # Merge cluster2 into cluster1
        cluster1.frame_ids.extend(cluster2.frame_ids)
        cluster1.timestamps.extend(cluster2.timestamps)
        
        # Update hash mappings
        old_rep = cluster2.representative_hash
        self._hash_to_cluster[old_rep] = idx1
        
        # Remove cluster2
        self._clusters.pop(idx2)
        
        # Rebuild hash-to-cluster mapping
        self._rebuild_hash_mapping()
        
        logger.debug(f"Merged clusters {idx1} and {idx2}, now {len(self._clusters)} clusters")
    
    def _rebuild_hash_mapping(self):
        """Rebuild hash-to-cluster mapping after merge"""
        self._hash_to_cluster = {}
        for cluster_id, cluster in enumerate(self._clusters):
            self._hash_to_cluster[cluster.representative_hash] = cluster_id
    
    def get_clusters(self) -> List[Cluster]:
        """Get all current clusters"""
        return self._clusters.copy()
    
    def get_representative_frames(self) -> List[Tuple[int, float]]:
        """
        Get representative frame (first frame) from each cluster.
        
        Returns:
            List of (frame_id, timestamp) tuples for representative frames
        """
        representatives = []
        for cluster in self._clusters:
            if cluster.frame_ids:
                representatives.append((cluster.frame_ids[0], cluster.timestamps[0]))
        
        # Sort by timestamp
        representatives.sort(key=lambda x: x[1])
        return representatives
    
    def get_summary(self) -> Dict[str, Any]:
        """Get clustering summary statistics"""
        if not self._clusters:
            return {
                'total_clusters': 0,
                'total_frames': 0,
                'compression_ratio': 0.0,
            }
        
        total_frames = sum(len(c.frame_ids) for c in self._clusters)
        compression_ratio = total_frames / len(self._clusters) if self._clusters else 0
        
        return {
            'total_clusters': len(self._clusters),
            'total_frames': total_frames,
            'compression_ratio': round(compression_ratio, 2),
            'avg_cluster_size': round(total_frames / len(self._clusters), 2),
            'max_cluster_size': max(len(c.frame_ids) for c in self._clusters),
            'min_cluster_size': min(len(c.frame_ids) for c in self._clusters),
        }
    
    def reset(self):
        """Reset all clustering state"""
        self._clusters = []
        self._hash_to_cluster = {}
        logger.debug("FrameClusterer reset")
