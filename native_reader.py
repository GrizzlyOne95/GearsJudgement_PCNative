"""Bounds-checked native UE3 fields shared by geometry serializers."""

class NativeLayoutError(ValueError):
    pass


class BoundedNativeWalker:
    def __init__(self, converter, start, end):
        if not 0 <= start <= end <= len(converter.src):
            raise NativeLayoutError("native export bounds are outside the package")
        self.converter = converter
        self.pos = start
        self.end = end

    def need(self, size):
        if size < 0 or self.pos < 0 or self.pos + size > self.end:
            raise NativeLayoutError(f"native field at {self.pos} overruns {self.end}")

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
            raise NativeLayoutError(f"invalid native array count {count} at {self.pos - 4}")
        for _ in range(count):
            element()
        return count

    def fixed_array(self, widths):
        return self.array(lambda: self.fields(widths), sum(widths))

    def bulk(self, widths):
        element_size = self.integer()
        if element_size != sum(widths):
            raise NativeLayoutError(f"native bulk width {element_size}, expected {sum(widths)} at {self.pos - 4}")
        return self.fixed_array(widths)

    def fname(self):
        self.need(8)
        if not self.converter.valid_fname(self.pos):
            raise NativeLayoutError("invalid native FName")
        self.fields([4, 4])

    def object_ref(self):
        self.need(4)
        self.converter.record_object_ref(self.pos)
        if not self.converter.valid_object_ref(self.integer()):
            raise NativeLayoutError("invalid native object reference")

    def string(self):
        length = self.integer()
        width, count = (2, -length) if length < 0 else (1, length)
        self.need(count * width)
        if count and any(self.converter.src[self.pos + (count - 1) * width:self.pos + count * width]):
            raise NativeLayoutError("unterminated native string")
        self.fields([width] * count)
