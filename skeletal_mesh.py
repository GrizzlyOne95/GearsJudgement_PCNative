"""Bounded v845 skeletal-mesh native serializer, taken from UnSkeletalMesh.cpp/.h.

This walks every field rather than swapping opaque words. Console GPU influence
bytes were reversed by the cooker; CPU vertex influence bytes were not.
"""
import struct


class MeshLayoutError(ValueError):
    pass


class SkeletalMeshWalker:
    def __init__(self, converter, start, end, has_vertex_colors=False):
        if not 0 <= start <= end <= len(converter.src):
            raise MeshLayoutError("mesh export bounds are outside the package")
        self.converter = converter
        self.pos = start
        self.end = end
        self.has_vertex_colors = has_vertex_colors

    def need(self, size):
        if size < 0 or self.pos < 0 or self.pos + size > self.end:
            raise MeshLayoutError(f"mesh field at {self.pos} overruns {self.end}")

    def fields(self, widths):
        self.need(sum(widths))
        self.pos = self.converter.swap_seq(self.pos, widths)

    def integer(self):
        self.need(4)
        result = self.converter.i32(self.pos)
        self.fields([4])
        return result

    def byte(self):
        self.need(1)
        result = self.converter.src[self.pos]
        self.pos += 1
        return result

    def array(self, element, min_width=1):
        count = self.integer()
        if count < 0 or count > (self.end - self.pos) // min_width:
            raise MeshLayoutError(f"invalid mesh array count {count} at {self.pos - 4}")
        for _ in range(count):
            element()
        return count

    def fixed_array(self, widths):
        return self.array(lambda: self.fields(widths), sum(widths))

    def bulk(self, widths):
        element_size = self.integer()
        if element_size != sum(widths):
            raise MeshLayoutError(f"mesh bulk width {element_size}, expected {sum(widths)} at {self.pos - 4}")
        return self.fixed_array(widths)

    def fname(self):
        self.need(8)
        if not self.converter.valid_fname(self.pos):
            raise MeshLayoutError("invalid mesh FName")
        self.fields([4, 4])

    def object_ref(self):
        if not self.converter.valid_object_ref(self.integer()):
            raise MeshLayoutError("invalid mesh object reference")

    def string(self):
        length = self.integer()
        width, count = (2, -length) if length < 0 else (1, length)
        self.need(count * width)
        if count and any(self.converter.src[self.pos + (count - 1) * width:self.pos + count * width]):
            raise MeshLayoutError("unterminated mesh string")
        self.fields([width] * count)

    def bone(self):
        self.fname()
        # Flags, VJointPos (quat + vector), child count, parent index, FColor.DWColor.
        self.fields([4] * 11)

    def section(self):
        self.fields([2, 2, 4, 4, 1])

    def chunk(self):
        self.fields([4])  # BaseVertexIndex
        # CPU vertices: float position, three DWORD normals, four float UVs,
        # DWORD color, then BYTE bone or BYTE bones + weights (no cook reversal).
        self.fixed_array([4] * 15 + [1])
        self.fixed_array([4] * 15 + [1] * 8)
        self.fixed_array([2])
        self.fields([4] * 3)  # NumRigidVertices, NumSoftVertices, MaxBoneInfluences

    def index_buffer(self):
        if self.integer() not in (0, 1):
            raise MeshLayoutError("invalid index-buffer CPU-access flag")
        width = self.byte()
        if width not in (2, 4):
            raise MeshLayoutError("unsupported mesh index width")
        self.bulk([width])

    def raw_points(self):
        self.need(16)
        flags, count, size, offset = struct.unpack_from(">Iiii", self.converter.src, self.pos)
        self.fields([4] * 4)
        # Empty/unused bulk headers consume no payload. Inline uncompressed INTs
        # are the only populated form modelled here; compressed/external data fails.
        if count == 0 and size == 0:
            if flags & ~(1 | 32):
                raise MeshLayoutError("unsupported empty raw-point bulk flags")
            return
        if flags != 0 or count < 0 or size != count * 4 or offset != self.pos:
            raise MeshLayoutError("unsupported raw-point bulk storage")
        self.need(size)
        for _ in range(count):
            self.fields([4])

    def gpu_vertices(self, lod_uvs, lod_vertices):
        num_uvs, full_precision, packed = self.integer(), self.integer(), self.integer()
        if num_uvs != lod_uvs or not 1 <= num_uvs <= 4:
            raise MeshLayoutError("inconsistent mesh UV count")
        if full_precision not in (0, 1) or packed not in (0, 1):
            raise MeshLayoutError("invalid mesh vertex format flags")
        self.fields([4] * 6)  # MeshExtension, MeshOrigin
        # TangentX/Z, reversed bone bytes, reversed weight bytes, position, UVs.
        widths = [4] * 4 + ([4] if packed else [4] * 3)
        widths += [4 if full_precision else 2] * (2 * num_uvs)
        if self.bulk(widths) != lod_vertices:
            raise MeshLayoutError("inconsistent mesh vertex count")
        self.converter.stats["skeletal_packed_lods" if packed else "skeletal_float_lods"] += 1

    def influence(self):
        self.fixed_array([4, 4])  # FVertexInfluence: weight DWORD, bone DWORD

        def mapping():
            self.fields([4, 4])  # FBoneIndexPair: two INTs
            self.fixed_array([4])

        self.array(mapping, 12)
        self.array(self.section, 13)
        self.array(self.chunk, 28)
        self.fixed_array([1])
        if self.byte() not in (0, 1):
            raise MeshLayoutError("unsupported alternate influence usage")

    def lod(self):
        self.array(self.section, 13)
        self.index_buffer()
        self.fixed_array([2])  # ActiveBoneIndices
        self.array(self.chunk, 28)
        size, num_vertices = self.integer(), self.integer()
        if size < 0 or num_vertices < 0:
            raise MeshLayoutError("negative mesh LOD size")
        self.fixed_array([1])  # RequiredBones
        self.raw_points()
        num_uvs = self.integer()
        self.gpu_vertices(num_uvs, num_vertices)
        if self.has_vertex_colors:
            if self.bulk([4]) != num_vertices:
                raise MeshLayoutError("inconsistent vertex-color count")
        self.array(self.influence, 21)

    def kdop(self):
        self.fields([4] * 6)  # RootBound min/max planes
        self.bulk([1] * 6)  # Compact min/max plane bytes
        self.bulk([2] * 4)  # Triangle vertex indices and material index
        self.fixed_array([4] * 3)  # CollisionVerts

    def walk(self):
        self.fields([4] * 7)  # FBoxSphereBounds
        self.array(self.object_ref, 4)
        self.fields([4] * 6)  # Origin / RotOrigin
        self.array(self.bone, 52)
        self.fields([4])  # SkeletalDepth
        self.array(self.lod, 80)

        def name_index():
            self.fname()
            self.fields([4])

        self.array(name_index, 12)
        self.array(self.kdop, 44)
        self.array(self.string, 4)  # BoneBreakNames
        self.fixed_array([1])  # BoneBreakOptions
        self.array(self.object_ref, 4)  # ClothingAssets
        self.fixed_array([4])  # CachedStreamingTextureFactors
        return self.pos
