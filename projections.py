import numpy as np
from typing import Tuple

from shifters import OpticalAxisShifter, EllipticShifter
from transformers import LinearTransformer, ExponentialTransformer, BiexponentialTransformer


class Projection():
    def __init__(self):
        pass


class EquidistantProjection(Projection):
    """ Equidistant projection that is perfectly aligned to zenith-north """
    def __init__(self):
        pass

    def __call__(self, x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        z = np.sqrt(np.square(x) + np.square(y))
        a = np.arctan2(y, x)
        return z, a

    def invert(self, z: np.ndarray, a: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        return z * np.sin(a), z * np.cos(a)


class BorovickaProjection(Projection):
    def __init__(self, *, a0: float=0, x0: float=0, y0: float=0, A: float=0, F: float=0, V: float=1,
            S: float=0, D: float=0, P: float=0, Q: float=0, epsilon: float=0, E: float=0):
        assert(epsilon >= 0 and V > 0)
        self.epsilon = epsilon                              # zenith angle of centre of FoV
        self.E = E                                          # azimuth angle of centre of FoV
        self.a0 = a0
        self.axis_shifter = EllipticShifter(a0, x0, y0, A, F, E)
        self.radial_transform = BiexponentialTransformer(V, S, D, P, Q)

    def __call__(self, x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        r, b = self.axis_shifter(x, y)
        u = self.radial_transform(r)

        if abs(self.epsilon) < 1e-14:                       # for tiny epsilon there is no displacement
            z = u                                           # and we are able to calculate the coordinates immediately
            a = self.E + b
        else:
            cosz = np.cos(u) * np.cos(self.epsilon) - np.sin(u) * np.sin(self.epsilon) * np.cos(b)
            z = np.arccos(cosz)
            sna = np.sin(b) * np.sin(u)
            cna = (np.cos(u) - np.cos(self.epsilon) * cosz) / np.sin(self.epsilon)
            a = self.E + np.arctan2(sna, cna)

        a = np.fmod(a, 2 * np.pi)                           # wrap around to [0, 2pi)
        return z, a

    def inverse(self, z: np.ndarray, a: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        a -= self.E