import numpy as np
from tqdm import tqdm
import sys


# Define global constants
mu_0 = 4 * np.pi * 1e-7  # Permeability of free space

# Simulation parameters
class CoilParameters:
    def __init__(self, length, height, turns):
        self.L = np.array(length)  # Store as a numpy array
        self.a = self.L / 2        # Calculate a based on L
        self.h = np.array(height)  # Store height as numpy array
        self.N = np.array(turns)   # Store number of turns as numpy array


# Program functions
def generate_range(a, grid_number):
    """
    Generates a sorted NumPy array of values ranging from -2*a to 2*a with a specified step size.
    Ensures that the array includes the values -2*a, 0, and 2*a, even if they are not part of the
    sequence generated by the specified step size.

    Parameters:
    -----------
    a : float
        The base value used to define the range boundaries. The function generates values
        starting from -2*a to 2*a.

    grid_number : float
        The step size between consecutive values in the generated array. This determines
        the spacing of the values within the range.

    Returns:
    --------
    np.ndarray
        A sorted 1D NumPy array containing values from -2*a to 2*a with the specified step size,
        including the values -2*a, 0, and 2*a.

    Example:
    --------
    >>> generate_range(1.5, 1.0)
    array([-3., -2., -1.,  0.,  1.,  2.,  3.])

    In this example:
    - `a` is 1.5, so the range is from -3.0 (-2*1.5) to 3.0 (2*1.5).
    - `grid_number` is 1.0, so the step size between values is 1.0.
    - The resulting array includes -3.0, 0.0, and 3.0, ensuring these critical points are present.
    """
    # Generate values from -2*a to 2*a with the specified step size
    range_vals = np.arange(-2 * a, 2 * a, grid_number)

    # Define critical values that must be included
    critical_vals = np.array([-2 * a, 0, 2 * a])

    # Combine and remove duplicates
    combined_vals = np.unique(np.concatenate((range_vals, critical_vals)))

    return combined_vals

def magnetic_field_square_coil(P, N, I, spire1, spire2):
    """
    Calculate the magnetic field at point P due to two square coils using the Biot-Savart Law.

    Parameters:
        P (np.ndarray): Observation point where the magnetic field is calculated (3x1 vector).
        N (int): Number of turns in each coil.
        I (float): Current flowing through each coil.
        spire1, spire2 (dict): Dictionaries representing each coil, with fields for 3D coordinates of segments.

    Returns:
        tuple: Total magnetic field (B), field from spire1 (B1), and field from spire2 (B2) as numpy arrays.
    """
    # Perform repetitive multiplication
    A1 = N * mu_0 * I / (4 * np.pi)

    # Initialize magnetic field vectors
    B1 = np.zeros(3)
    B2 = np.zeros(3)

    # Calculate differential elements
    dl_1 = np.diff(spire1, axis=2)  # Differential length element for coil 1
    dl_2 = np.diff(spire2, axis=2)  # Differential length element for coil 2

    for i in range(spire1.shape[0]):
        for j in range(dl_1.shape[2]):
            # Calculate position vector R1 from the segment of spire1 to point P
            R1 = P - spire1[i, :, j]  # Ensure R1 is a numpy array

            # Calculate the position vector R2 from the segment of coil 2 to point P
            R2 = P - spire2[i, :, j]  # Ensure R2 is a numpy array
           
            # Biot-Savart law: Calculate differential magnetic fields
            dB1 = (A1) * np.cross(dl_1[i,: , j], R1) / np.linalg.norm(R1)**3
            dB2 = (A1) * np.cross(dl_2[i,: , j], R2) / np.linalg.norm(R2)**3

            # Sum differential contributions
            B1 += dB1
            B2 += dB2

    # Total magnetic field at point P
    B = B1 + B2# Magnetic permeability of vacuum

    return B, B1, B2


def square_spires(A, h, a, num_seg):
    """
    Genera las coordenadas de dos espiras cuadradas (coils) en el plano Y-Z,
    aplicando una matriz de rotación para orientarlas en el espacio 3D.

    Parámetros:
    -----------
    A : numpy.ndarray
        Matriz de rotación 3x3 para orientar las espiras en el espacio 3D.
    h : float
        Altura de las espiras a lo largo del eje X.
    a : float
        Longitud/2 de las espiras en el plano Y-Z.
    num_seg : int
        Número de segmentos en cada lado de las espiras.

    Retorna:
    --------
    spire1, spire2 : numpy.ndarray
        Arrays 3D que contienen las coordenadas de las dos espiras. Cada array tiene
        una forma de (4, 3, num_seg), donde:
        - El primer eje corresponde a los 4 lados.
        - El segundo eje corresponde a las coordenadas X, Y y Z.
        - El tercer eje corresponde a los segmentos de cada lado.
    """
    def create_side(x, y, z):
        """Crea las coordenadas para un lado de la espira."""
        return np.array([x, y, z])

    # Coordenadas base para los lados
    h_half = h / 2
    L_half = a
    y_coords = np.linspace(L_half, -L_half, num_seg)
    z_coords = np.linspace(-L_half, L_half, num_seg)

    sides = np.array([
        create_side(h_half * np.ones(num_seg), y_coords, L_half * np.ones(num_seg)),   # Side facing -Y direction (bottom)
        create_side(h_half * np.ones(num_seg), -L_half * np.ones(num_seg), y_coords),  # Side facing -Z direction (left)
        create_side(h_half * np.ones(num_seg), z_coords, -L_half * np.ones(num_seg)),  # Side facing +Y direction (top)
        create_side(h_half * np.ones(num_seg), L_half * np.ones(num_seg), z_coords),   # Side facing +Z direction (right)
    ])

    # Aplicar rotación para la primera espira
    spire1 = np.einsum('ij,ljk->lik', A, sides)

    # Ajustar el desplazamiento para la segunda espira
    displacement = np.array([h, 0, 0]).reshape(3, 1)  # Ajustar para que sea compatible con broadcasting
    spire2 = np.einsum('ij,ljk->lik', A, sides - displacement[None, :, :])

    return spire1, spire2
   

def coil_simulation_1d(range_vals, A, coil_params, current, num_seg):
    # Define the coil geometry and calculate fields
    X, Y = np.meshgrid(range_vals, range_vals)
    # Initialize coil dictionary to store results
    coil = {}
    # Define storage for results
    coil['xy'] = {'X': X, 'Y': Y, 'Bx': np.nan * np.ones_like(X), 'By': np.nan * np.ones_like(Y), 'Bz': np.nan * np.ones_like(Y), 'norB': np.nan * np.ones_like(Y)}
    coil['yz'] = {'Y': X, 'Z': Y, 'Bx': np.nan * np.ones_like(X), 'By': np.nan * np.ones_like(Y), 'Bz': np.nan * np.ones_like(Y), 'norB': np.nan * np.ones_like(Y)}
    coil['xz'] = {'X': X, 'Z': Y, 'Bx': np.nan * np.ones_like(X), 'By': np.nan * np.ones_like(Y), 'Bz': np.nan * np.ones_like(Y), 'norB': np.nan * np.ones_like(Y)}
   
    coil['spire1'], coil['spire2'] = square_spires(A, coil_params.h, coil_params.L, num_seg)

    # Loop through the grid to calculate the magnetic field
    num_iter = len(X) ** 2

    # Initialize a progress bar
    progress_bar = tqdm(total=num_iter, desc="Simulation Progress")
    for i in range(len(X)):  # Loop over X values
        for j in range(len(Y)):  # Loop over Y values
            # Evaluate magnetic field in the X-Y plane
            P1 = np.array([X[i, j], Y[i, j], 0])
            B1, _, _ = magnetic_field_square_coil(P1, coil_params.N, current, coil['spire1'], coil['spire2'])
            coil['xy']['Bx'][i, j], coil['xy']['By'][i, j], coil['xy']['Bz'][i, j] = B1
            coil['xy']['norB'][i, j] = np.linalg.norm(B1)

            # Evaluate magnetic field in the Y-Z plane
            P2 = np.array([0, X[i, j], Y[i, j]])
            B2, _, _ = magnetic_field_square_coil(P2, coil_params.N, current, coil['spire1'], coil['spire2'])
            coil['yz']['Bx'][i, j], coil['yz']['By'][i, j], coil['yz']['Bz'][i, j] = B2
            coil['yz']['norB'][i, j] = np.linalg.norm(B2)

            # Evaluate magnetic field in the X-Z plane
            P3 = np.array([X[i, j], 0, Y[i, j]])
            B3, _, _ = magnetic_field_square_coil(P3, coil_params.N, current, coil['spire1'], coil['spire2'])
            coil['xz']['Bx'][i, j], coil['xz']['By'][i, j], coil['xz']['Bz'][i, j] = B3
            coil['xz']['norB'][i, j] = np.linalg.norm(B3)
            
            # Update progress bar
            progress_bar.update(1)

    # Close the progress bar once the simulation is complete
    progress_bar.close()

    return coil