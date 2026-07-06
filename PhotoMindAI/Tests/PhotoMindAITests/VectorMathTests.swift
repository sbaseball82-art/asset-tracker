import Testing
@testable import PhotoMindAI

struct VectorMathTests {
    @Test func normalizedIsUnitLength() {
        let v: [Float] = [3, 4]        // length 5
        let n = VectorMath.normalized(v)
        let len = (n[0] * n[0] + n[1] * n[1]).squareRoot()
        #expect(abs(len - 1) < 1e-5)
    }

    @Test func zeroVectorReturnedUnchanged() {
        let v: [Float] = [0, 0, 0]
        #expect(VectorMath.normalized(v) == v)
    }

    @Test func cosineOfIdenticalVectorsIsOne() {
        let v = VectorMath.normalized([0.1, 0.2, 0.3, 0.4, 0.5])
        #expect(abs(VectorMath.cosine(v, v) - 1) < 1e-5)
    }

    @Test func cosineOfOrthogonalIsZero() {
        let a = VectorMath.normalized([1, 0, 0, 0])
        let b = VectorMath.normalized([0, 1, 0, 0])
        #expect(abs(VectorMath.cosine(a, b)) < 1e-5)
    }

    @Test func cosineHandlesUnrolledRemainder() {
        // 6 elements exercises both the 4-wide loop and the 2-element tail.
        let a = VectorMath.normalized([1, 1, 1, 1, 1, 1])
        let b = VectorMath.normalized([1, 1, 1, 1, 1, 1])
        #expect(abs(VectorMath.cosine(a, b) - 1) < 1e-5)
    }

    @Test func mismatchedDimensionsAreSafe() {
        #expect(VectorMath.cosine([1, 2], [1, 2, 3]) == -1)
    }
}
