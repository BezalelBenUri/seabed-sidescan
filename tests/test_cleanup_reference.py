"""Independent flood-fill and explicit-ring reference for patch cleanup."""

from collections import Counter

import numpy as np
import pytest

from seabed_sidescan.cleanup import remove_small_patches


def brute_cleanup(classified, valid, min_patch_size, nodata_label):
    """Enumerate 8-connected components and rings using Python sets."""
    cleaned = classified.copy()
    patches = {}
    removed = {}
    for label in sorted(int(value) for value in np.unique(classified) if value != nodata_label):
        remaining = set(map(tuple, np.argwhere((classified == label) & valid)))
        patches[label] = 0
        while remaining:
            first = remaining.pop()
            component = {first}
            frontier = [first]
            while frontier:
                row, col = frontier.pop()
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        neighbor = (row + dy, col + dx)
                        if neighbor in remaining:
                            remaining.remove(neighbor)
                            component.add(neighbor)
                            frontier.append(neighbor)
            patches[label] += 1
            if len(component) >= min_patch_size:
                continue
            ring = set()
            for row, col in component:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nr, nc = row + dy, col + dx
                        if 0 <= nr < classified.shape[0] and 0 <= nc < classified.shape[1]:
                            ring.add((nr, nc))
            ring.difference_update(component)
            counts = Counter(int(classified[row, col]) for row, col in ring
                             if classified[row, col] != nodata_label)
            if not counts:
                continue
            winner, count = counts.most_common(1)[0]
            if count <= sum(counts.values()) / 2:
                continue
            for row, col in component:
                cleaned[row, col] = winner
            removed[label] = removed.get(label, 0) + len(component)
    cleaned[~valid] = nodata_label
    return cleaned, patches, removed


@pytest.mark.parametrize("seed", [0, 7, 612])
@pytest.mark.parametrize("nodata_label", [0, 255])
@pytest.mark.parametrize("min_patch_size", [1, 4, 15])
def test_patch_cleanup_matches_independent_flood_fill(seed, nodata_label, min_patch_size):
    rng = np.random.default_rng(seed)
    classes = np.array([0, 7, 42, 255] if nodata_label == 255 else [0, 2, 7, 42], dtype="uint8")
    classified = rng.choice(classes, size=(13, 17))
    valid = classified != nodata_label
    expected = brute_cleanup(classified, valid, min_patch_size, nodata_label)
    actual = remove_small_patches(classified, valid, min_patch_size, nodata_label)
    np.testing.assert_array_equal(actual[0], expected[0])
    assert actual[1:] == expected[1:]


def test_patch_rings_match_at_raster_edges_and_holes():
    classified = np.full((17, 19), 4, dtype="uint8")
    classified[:2, :2] = 17  # top/left raster edge
    classified[-2:, -3:] = 17  # bottom/right edge
    classified[5:12, 5:12] = 0  # hole separates islands from surrounding class
    classified[7:9, 7:9] = 17  # isolated island has no valid neighbouring class
    classified[4:7, 14:17] = 17
    classified[5, 15] = 0  # a NoData hole inside an island
    classified[11:13, 14:16] = 42
    classified[12:14, 15:17] = 42  # diagonal connection is one component
    valid = classified != 0
    expected = brute_cleanup(classified, valid, 15, 0)
    actual = remove_small_patches(classified, valid, 15, 0)
    np.testing.assert_array_equal(actual[0], expected[0])
    assert actual[1:] == expected[1:]
    assert np.all(actual[0][7:9, 7:9] == 17)
    assert np.all(actual[0][:2, :2] == 4)


def test_patch_cleanup_is_class_label_permutation_invariant():
    rng = np.random.default_rng(208)
    classified = rng.choice(np.array([0, 2, 7, 42], dtype="uint8"), (19, 23))
    forward = {0: 0, 2: 72, 7: 13, 42: 3}
    inverse = {value: key for key, value in forward.items()}
    remapped = np.vectorize(forward.__getitem__, otypes=[np.uint8])(classified)
    first, patches, removed = remove_small_patches(classified, classified != 0, 10, 0)
    second, mapped_patches, mapped_removed = remove_small_patches(remapped, remapped != 0, 10, 0)
    restored = np.vectorize(inverse.__getitem__, otypes=[np.uint8])(second)
    np.testing.assert_array_equal(restored, first)
    assert {inverse[key]: value for key, value in mapped_patches.items()} == patches
    assert {inverse[key]: value for key, value in mapped_removed.items()} == removed
