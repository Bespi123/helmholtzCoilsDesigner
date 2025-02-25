# Import dependencies
import numpy as np
import pandas as pd
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
from typing import Union

#from scipy.optimize import minimize  # Optimization function from SciPy
#import parallel_test4 as simulation  # Custom simulation module
#import numpy as np  # Numerical computations

# Define global constants
MU_0 = 4 * np.pi * 1e-7  # Permeability of free space
rotz_180 = np.array([
    [-1, 0, 0],
    [0, -1, 0],
    [0, 0, 1]
])

class CoilParameters:
    def __init__(self, coils_number: int, length: Union[float, list, np.ndarray], 
                 height: Union[float, list, np.ndarray], turns: Union[int, list, np.ndarray], 
                 current: float, rot_matrix: np.ndarray):
        """
        Initialize Helmholtz coil parameters.

        Args:
            coils_number (int): Number of Helmholtz coils.
            length (float | list | np.ndarray): Length(s) of the Helmholtz testbed side.
            height (float | list | np.ndarray): Distance(s) between Helmholtz coils.
            turns (int | list | np.ndarray): Number of turns in each coil.
            current (float): Electric current applied to the coils.
            rot_matrix (np.ndarray): Rotation matrix for coordinate transformation.
        """
        # Convert inputs to NumPy arrays
        self.L = np.atleast_1d(length)  
        self.h = np.atleast_1d(height)   
        self.N = np.atleast_1d(turns) if isinstance(turns, (list, np.ndarray)) else np.array([turns])  
        self.I = current
        self.A = rot_matrix

        # Other parameters
        self.coils_number = coils_number
        
        # Validate and expand `length`
        if self.L.shape[0] not in {1, coils_number}:
            raise ValueError(f"Invalid length size. Expected 1 or {coils_number}, got {self.L.shape[0]}")
        elif self.L.shape[0] == 1:
            self.L = self.L[0] * np.ones((coils_number,))

        # Validate and expand `height`
        if self.h.shape[0] not in {1, coils_number - 1}:
            raise ValueError(f"Invalid height size. Expected 1 or {coils_number - 1}, got {self.h.shape[0]}")
        elif self.h.shape[0] == 1:
            self.h = self.h[0] * np.ones((coils_number - 1,))

        # Validate and expand `turns`
        if self.N.shape[0] not in {1, coils_number}:
            raise ValueError(f"Invalid turns size. Expected 1 or {coils_number}, got {self.N.shape[0]}")
        elif self.N.shape[0] == 1:
            self.N = self.N[0] * np.ones((coils_number,), dtype=int)

        # Validate `rot_matrix`
        if self.A.shape != (3, 3):
            raise ValueError(f"Invalid rotation matrix shape. Expected (3,3), got {self.A.shape}")
        
        self.a = self.L / 2  # Half Helmholtz testbed length side
        self.pos =  self.get_spires_position()


    def get_spires_position(self):
        """
        Compute the positions of the spires in the Helmholtz coil system.

        Returns:
            np.ndarray: Array with computed positions.
        """
        coils_number = self.coils_number  # Number of coils
        h = self.h  # Heights between coils

        # Initialize arrays with NaN values
        d = np.full(coils_number, np.nan)   # Temporary array for displacement values
        d1 = np.full(coils_number, np.nan)  # Final array for cumulative positions

        o = coils_number // 2  # Compute middle index (integer division)

        # Compute displacement values for each coil except the last one
        for j in range(coils_number - 1):
            if j < o - (coils_number % 2 == 0):  
                # For coils before the middle point
                d[j] = -h[j]  
            elif j == o - (coils_number % 2 == 0):  
                # Middle coil case: If even, split height; if odd, set zero
                d[j] = -h[j] / 2 if coils_number % 2 == 0 else 0
                d[j + 1] = h[j] / 2 if coils_number % 2 == 0 else h[j]
            else:
                # For coils after the middle point
                d[j + 1] = h[j]              

        # Compute cumulative positions
        for j in range(coils_number):
            if j <= o - (coils_number % 2 == 0):  
                # Sum displacements from current position to the middle point
                d1[j] = np.sum(d[j:o - (coils_number % 2 == 0) + 1]) 
            else:
                # Sum displacements from the middle point onward
                d1[j] = np.sum(d[o - (coils_number % 2 == 0) + 1:j + 1]) 

        return d1  # Return computed coil positions

    def square_spires(self, num_seg, b=None):
        """
        Generates coordinates for multiple square or rectangular coils in 3D space, transformed by matrix A.

        Parameters:
        num_seg (int): Number of segments per side.
        b (float, optional): Half the vertical side length (along the Z-axis). If not provided, b = a (square).t

        Returns:
            list: List of arrays, each representing a coil shape (4, 3, num_seg).
        """
        # Use `b = a` if not provided
        b = np.atleast_1d(b) if b is not None else self.a

        spires = []

        for i in range(self.coils_number):
            h = self.h[i] if i < self.h.shape[0] else self.h[i-1]
            L0_half = self.a[i]
            L1_half = b[i]

            # Generate evenly spaced points for the y and z coordinates along the square sides
            y_coords = np.linspace(L0_half, -L0_half, num_seg)
            z_coords = np.linspace(-L1_half, L1_half, num_seg)

            # Define the 3D coordinates of the four sides of a square coil
            spire = np.array([
                [np.zeros(num_seg), y_coords, L1_half * np.ones(num_seg)],   # Top edge
                [np.zeros(num_seg), -L0_half * np.ones(num_seg), -z_coords], # Right edge
                [np.zeros(num_seg), -y_coords, -L1_half * np.ones(num_seg)], # Bottom edge
                [np.zeros(num_seg), L0_half * np.ones(num_seg), z_coords]    # Left edge
            ])

            displacement = np.array([self.pos[i], 0, 0]).reshape(3, 1)

            # Transform the coordinates of the second coil using the matrix A and apply the displacement
            spire = np.einsum('ij,ljk->lik', self.A, spire - displacement[None,: , :])

            spires.append(spire)
        return spires
    
    

    def circular_spires(self, num_seg):
        """
        Generates coordinates of two circular coils (spirals) in 3D space, divided into four quadrants.
    
        Parameters:
            num_seg (int): Number of segments per side.
    
        Returns:
            list: List of arrays, each representing a coil shape (4, 3, num_seg).
        """
        spires = []

        for i in range(self.coils_number):
            r = self.L[i] / 2

            # Generate angle values for the circular motion (theta)
            theta_vals = 2 * np.pi - np.linspace(0, 2 * np.pi, 4 * num_seg)  # Full circle (360°)
    
            # Parametrize the circular spiral in 3D space
            x_coords = np.zeros(4 * num_seg)                    # x remains constant
            y_coords = r * np.sin(theta_vals)    # y = r * sin(theta), circular pattern in the y-direction
            z_coords = r * np.cos(theta_vals)    # z = r * cos(theta), circular pattern in the z-direction
    
            # Stack the coordinates into a 2D array (shape: [4*num_seg, 3])
            spiral_coords = np.array([x_coords, y_coords, z_coords]).T
    
            # Divide the spiral into four quadrants, each containing `num_seg` points
            half_num_seg = num_seg
            sides = np.array([
                spiral_coords[:half_num_seg],           # First quadrant
                spiral_coords[half_num_seg:2*half_num_seg],  # Second quadrant
                spiral_coords[2*half_num_seg:3*half_num_seg],  # Third quadrant
                spiral_coords[3*half_num_seg:],        # Fourth quadrant
            ])
    
            # Transpose the sides to match the required shape for transformation (shape: [4, 3, num_seg])
            sides = sides.transpose(0, 2, 1)

            displacement = np.array([self.pos[i], 0, 0]).reshape(3, 1)
            
            # Transform the coordinates of the second coil using the matrix A and apply the displacement
            spire = np.einsum('ij,ljk->lik', self.A, sides - displacement[None,: , :])

            spires.append(spire)
    
        # Return the coordinates of both spirals
        return spires
    
    def polygonal_spires(self, num_seg, n=5):
        """
        Generates coordinates for two polygonal coils in 3D, divided into 4 equal groups.

        Parameters:
            num_seg (int): Total number of segments to distribute along all edges.
            n (int): Number of sides of the polygon (e.g., 5 = pentagon).

        Returns:
            list: A list containing transformed coordinates of the polygonal spirals, divided into four quadrants.
        """
        total_num_seg = 4 * num_seg
        seg_per_edge = round(total_num_seg / n)  # Avoid loss of points

        # Generate evenly spaced vertices
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
        spires = []

        for coil_idx in range(self.coils_number):  # Avoid overwriting `i`
            r = self.L[coil_idx] / 2
            y_vertices = r * np.sin(angles)
            z_vertices = r * np.cos(angles)

            # Close the polygon
            y_closed = np.append(y_vertices, y_vertices[0])
            z_closed = np.append(z_vertices, z_vertices[0])

            # Generate edges
            poly_edges = []
            for j in range(n):  # Use `j` instead of `i`
                y_edge = np.linspace(y_closed[j], y_closed[j+1], seg_per_edge)
                z_edge = np.linspace(z_closed[j], z_closed[j+1], seg_per_edge)
                x_edge = np.zeros(seg_per_edge)
                poly_edges.append(np.vstack((x_edge, y_edge, z_edge)).T)
        
            poly_edges = np.array(poly_edges).reshape(-1, 3)

            # Split edges into 4 quadrants dynamically
            groups = np.array_split(poly_edges, 4)

            sides = np.array([g.T for g in groups])  # Shape: [4, 3, points_per_group]

            displacement = np.array([self.pos[coil_idx], 0, 0]).reshape(3, 1)

            # Transform the coordinates using matrix A and apply displacement
            spire = np.einsum('ij,ljk->lik', np.dot(self.A, rotz_180), sides - displacement[None, :, :])
            spires.append(spire)

        return spires

    def star_spires(self, num_seg, star_points=6):
        """
        Generates coordinates for two star-shaped coils (spires) in 3D space,
        divided into 4 equal groups of edges.
        
        Parameters:
            A (ndarray): A 3x3 transformation matrix to rotate or transform the star coordinates.
            h (float): Separation between the spires (displacement along the x-axis).
            r (float): Outer radius of the star.
            num_seg (int): Number of segments (points) to be distributed among all edges of the star.
            star_points (int): Number of star points (default is 6, yielding 12 vertices with alternating outer and inner).
            
        Returns:
            tuple: (spire1, spire2) each of shape (4, 3, group_size * seg_per_edge)
                where 4 is the number of groups,
                3 corresponds to (x, y, z),
                and group_size * seg_per_edge is the total points in each group.
        """
        total_num_seg = 4*num_seg
        total_vertices = star_points * 2  # Total vertices (e.g., 12 for a 6-point star)
        seg_per_edge = total_num_seg // total_vertices  # Ensure integer division
        
        # Generate angles for each vertex
        angles = np.linspace(0, 2*np.pi, total_vertices, endpoint=False)
        
        spires = []

        for coil_idx in range(self.coils_number): 
            r = self.L[coil_idx] / 2
            # Alternating radii for outer and inner points
            radii = np.empty(total_vertices)
            radii[0::2] = r          # Outer points (even indices)
            radii[1::2] = r / 2      # Inner points (odd indices)
        
            # Compute y and z coordinates of the vertices
            y_vertices = radii * np.sin(angles)
            z_vertices = radii * np.cos(angles)
        
            # Close the star by repeating the first vertex at the end
            y_closed = np.append(y_vertices, y_vertices[0])
            z_closed = np.append(z_vertices, z_vertices[0])
        
            # Generate edges by interpolating between consecutive vertices
            star_edges = []
            for i in range(total_vertices):
                # Linearly interpolate between the current and next vertex
                y_edge = np.linspace(y_closed[i], y_closed[i+1], seg_per_edge)
                z_edge = np.linspace(z_closed[i], z_closed[i+1], seg_per_edge)
                x_edge = np.zeros(seg_per_edge)  # X-coordinate is h/2 for the first spire
            
                # Stack coordinates into (seg_per_edge, 3) array and add to the list
                edge_coords = np.vstack((x_edge, y_edge, z_edge)).T
                star_edges.append(edge_coords)
        
            # Convert list of edges to a numpy array (shape: [total_vertices, seg_per_edge, 3])
            star_edges = np.array(star_edges)
            star_edges = star_edges.reshape(-1, 3)
        
            points_per_group = np.size(star_edges,0) // 4

            groups = []
            for i in range(4):
                # Select the edges for the current group
                group_edges = star_edges[i*points_per_group : (i+1)*points_per_group]
                # Combine all points in these edges into a single array (shape: [edges_per_group * seg_per_edge, 3])
                group_points = group_edges.reshape(-1, 3)
                # Transpose to shape (3, edges_per_group * seg_per_edge) for transformation
                groups.append(group_points.T)
        
            # Convert groups to a numpy array (shape: [4, 3, group_points_per_group])
            sides = np.array(groups)

            # Apply transformation matrix A to the first spire
            #spire1 = np.einsum('ij,ljk->lik', np.dot(A, rotz_180), sides)
        
            # Compute coordinates for the second spire (shifted by -h along x-axis before transformation)
            displacement = np.array([self.pos[coil_idx], 0, 0]).reshape(3, 1)
            spire = np.einsum('ij,ljk->lik', np.dot(self.A, rotz_180), sides - displacement)
            spires.append(spire)

        return spires


    def __repr__(self):
        return (f"CoilParameters(coils_number={self.coils_number}, L={self.L}, h={self.h}, "
                f"N={self.N}, I={self.I}, A_shape={self.A.shape})")


def generate_range(x_range, y_range=None, z_range=None, step_size_x=0.1, step_size_y=None, step_size_z=None):
    """
    Generates a sorted NumPy array of values covering the given ranges with a specified step size.
    If only x_range is provided, y_range and z_range will be set to x_range.
    If only step_size_x is provided, step_size_y and step_size_z will be set to step_size_x.

    Parameters:
        x_range, y_range, z_range (tuple): (min, max) values for each axis.
        step_size_x, step_size_y, step_size_z (float): Step sizes for each axis.

    Returns:
        X_unique, Y_unique, Z_unique (numpy.ndarray): Unique coordinates in the XY, YZ, and XZ planes.
    """
    # If y_range and z_range are not provided, set them equal to x_range
    if y_range is None:
        y_range = [-0, 0]
    if z_range is None:
        z_range = [-0, 0]

    # If step_size_y and step_size_z are not provided, set them equal to step_size_x
    if step_size_y is None:
        step_size_y = step_size_x
    if step_size_z is None:
        step_size_z = step_size_x

    # Generate values from -2*a to 2*a with a step size of step_size
    range_vals_x = np.arange(x_range[0], x_range[1] + step_size_x, step_size_x)
    range_vals_y = np.arange(y_range[0], y_range[1] + step_size_y, step_size_y)
    range_vals_z = np.arange(z_range[0], z_range[1] + step_size_z, step_size_z)
    
    # Ensure critical points (-2*a, 0, and 2*a) are included in the range
    critical_vals_x = np.array([x_range[0], 0, x_range[1]])
    critical_vals_y = np.array([y_range[0], 0, y_range[1]])
    critical_vals_z = np.array([z_range[0], 0, z_range[1]])
    range_vals_x = np.unique(np.concatenate((range_vals_x, critical_vals_x)))
    range_vals_y = np.unique(np.concatenate((range_vals_y, critical_vals_y)))
    range_vals_z = np.unique(np.concatenate((range_vals_z, critical_vals_z)))
    
    # Create a meshgrid for the XY, YZ, and XZ planes
    X, Y = np.meshgrid(range_vals_x, range_vals_y)
    
    # Points in the XY plane (Z = 0)
    X_xy, Y_xy = X.flatten(), Y.flatten()
    Z_xy = np.zeros_like(X_xy)
    
    # Points in the YZ plane (X = 0)
    Y, Z = np.meshgrid(range_vals_y, range_vals_z)    
    Y_yz, Z_yz = Y.flatten(), Z.flatten()
    X_yz = np.zeros_like(Y_yz)
    
    # Points in the XZ plane (Y = 0)
    X, Z = np.meshgrid(range_vals_x, range_vals_z)    
    X_xz, Z_xz = X.flatten(), Z.flatten()
    Y_xz = np.zeros_like(X_xz)
    
    # Concatenate all points
    X_total = np.concatenate([X_xy, X_yz, X_xz])
    Y_total = np.concatenate([Y_xy, Y_yz, Y_xz])
    Z_total = np.concatenate([Z_xy, Z_yz, Z_xz])
    
    # Combine coordinates into a single array of shape (N, 3)
    points = np.column_stack((X_total, Y_total, Z_total))
    
    # Remove duplicate points
    unique_points = np.unique(points, axis=0)
    
    # Split the unique points back into X, Y, Z
    X_unique, Y_unique, Z_unique = unique_points[:, 0], unique_points[:, 1], unique_points[:, 2]
    
    return X_unique, Y_unique, Z_unique


def calculate_field(args):
    """
    Calculates the magnetic field at a given point due to a current-carrying coil.
    
    Parameters:
        args (tuple): A tuple containing:
            A1 (float): Proportionality constant for the magnetic field (e.g., permeability times current).
            P (numpy.ndarray): The point in 3D space where the magnetic field is calculated (shape: (3,)).
            side (numpy.ndarray): 3D coordinates of the coil segments (shape: (num_sides, 3, num_points)).
    
    Returns:
        numpy.ndarray: The magnetic field vector (shape: (3,)).
    """
    A1, P, side = args
    B = np.zeros(3)  # Initialize the magnetic field vector to zero
    dl = np.diff(side, axis=2)  # Differential length elements for each segment of the coil
    
    # Loop over each side of the coil
    for k in range(side.shape[0]):
        # Loop over each differential length element in the current side
        for j in range(dl.shape[2]):
            # Vector from the differential element to the point of interest
            R = P - side[k, :, j]
            
            # Calculate the contribution to the magnetic field (Biot-Savart Law)
            dB = (A1) * np.cross(dl[k, :, j], R) / np.linalg.norm(R)**3
            
            # Accumulate the contribution to the total magnetic field
            B += dB
    
    return B


def magnetic_field_square_coil_parallel(P, N, I, coils, n):
    """
    Calculates the magnetic field at observation points P due to two square coils
    using the Biot-Savart Law.

    Parameters:
        P (np.ndarray): Observation points where the magnetic field is calculated (matrix of size m x 3).
        N (int): Number of turns in each coil.
        I (float): Current flowing through each coil.
        coils (np.ndarray): 3D coordinates of the coil segments (array of size num_seg x 3 x num_points).
        n (int): Number of segments per coil to process simultaneously.

    Returns:
        np.ndarray: Total magnetic field (B) calculated at each observation point P (matrix of size m x 3).
    """
    # Proportionality constant from the Biot-Savart Law
    A1 = (N * MU_0 * I) / (4 * np.pi)

    # Use multiprocessing to calculate in parallel
    with Pool(processes=cpu_count()) as pool:
        B_segments = []  # List to store magnetic field results for each observation point
        
        # Iterate over each observation point in P
        for i in range(P.shape[0]):  # P has m rows, each representing a point in space
            # Prepare arguments for each segment of the coil
            args = [(A1, P[i, :], coils[j:j+n, :, :]) for j in range(0, coils.shape[0], n)]
            
            # Compute the magnetic field in parallel for coil segments
            B_segments.append(pool.map(calculate_field, args))

        # Sum contributions from all segments to get the total field at each point P
        B_results = [np.sum(segments, axis=0) for segments in B_segments]

    # Return results as a NumPy array
    return np.array(B_results)


def coil_simulation_1d_sequential(X, Y, Z, coil_params, current, spires_list, parallel_coils, batch_size, enable_progress_bar=True):
    """
    Simulates the magnetic field generated by two coils on a 1D grid in three orthogonal planes.

    Parameters:
        grid_number (float): Step size for generating the grid.
        coil_params (CoilParameters): Parameters of the coils, including length, height, and turns.
        current (float): Current flowing through the coils.
        coil1, coil2 (np.ndarray): 3D coordinates of the two coils (arrays of shape num_segments x 3 x num_points).
        parallel_coils (int): Number of coil segments processed simultaneously.
        batch_size (int): Number of points to process in each batch.

    Returns:
        pd.DataFrame: A DataFrame containing the grid coordinates and magnetic field components.
                      Columns: ['X', 'Y', 'Z', 'Bx', 'By', 'Bz'].
    """
    # Generate the X-Y grid based on the coil dimensions and grid step size
    #X, Y = generate_range(coil_params.a, grid_number)
    
    result = []  # List to store the simulation results
    coils = np.concatenate([spire[np.newaxis, ...] for spire in spires_list], axis=0)
    #coils = np.concatenate([coil1, coil2], axis=0)  # Combine both coils into a single array
    #print(f"Shape of concatenated coils: {coils.shape}") 

    # Flatten X and Y arrays for easier iteration over the grid points
    X_flat = X.flatten()
    Y_flat = Y.flatten()
    Z_flat = Z.flatten()

    if X.ndim > 1:
        m = X.shape[1]  # Number of columns in X and Y (3 in this example)
    else:
        m = 1

    # Calculate the total number of iterations for progress tracking
    num_iter = len(X_flat) + len(Y_flat) + len(Z_flat)
    
    progress_bar = tqdm(total=num_iter, desc="Simulation Progress", disable=not enable_progress_bar)

    # Iterate over the grid points in batches
    for k in range(0, len(X_flat), batch_size):
        X_batch = X_flat[k: k + batch_size]  # Batch of X coordinates
        Y_batch = Y_flat[k: k + batch_size]  # Batch of Y coordinates
        Z_batch = Z_flat[k: k + batch_size]  # Batch of Y coordinates

       # Generate 3D points for each batch in three orthogonal planes
        P_batch = np.stack([X_batch, Y_batch, Z_batch], axis=1)

        # Calculate the magnetic field at the batch points
        B = magnetic_field_square_coil_parallel(P_batch, coil_params.N, current, coils, parallel_coils)

        # Store the results in the format (X, Y, Z, Bx, By, Bz)
        result += list(zip(P_batch[:, 0], P_batch[:, 1], P_batch[:, 2], B[:, 0], B[:, 1], B[:, 2]))

        # Update the progress bar
        progress_bar.update(batch_size)

    if progress_bar.n < progress_bar.total:
        progress_bar.update(progress_bar.total - progress_bar.n)

    # Close the progress bar once the simulation is complete
    progress_bar.close()

    # Convert the results to a DataFrame for easier data manipulation and visualization
    return pd.DataFrame(result, columns=['X', 'Y', 'Z', 'Bx', 'By', 'Bz'])



def objective(variables, A, target_bx, grid_length_size=0.01, num_seg=100):
    """
    Objective function with additional parameters.
    
    Parameters:
    - variables: List of [length, distance] to optimize.
    - A: Transformation matrix for the spires.
    - target_bx: Target value for Bx in the optimization.
    - grid_length_size: Step size for the simulation grid (default: 0.01).
    - num_seg: Number of segments for the spires (default: 100).

    Returns:
    - Objective function value.
    """
    length, distance = variables  # Extract length and distance variables
    turns = 30  # Number of turns for the coil
    I = 1  # Current in the coil
    
    # Initialize coil parameters
    coil = CoilParameters(length, distance, turns)

    # Generate coil spires and simulation grid
    spire1_s, spire2_s = square_spires(A, coil.h, coil.a, num_seg)
    X = np.arange(-coil.a, coil.a, grid_length_size)  # X-axis points
    Y = np.zeros_like(X)  # Y-axis remains zero (1D simulation)

    # Run the simulation
    x_coil_results_s = coil_simulation_1d_sequential(
        X, Y, coil, I, spire1_s, spire2_s, 1, 20
    )
    bx_line = x_coil_results_s[
        (x_coil_results_s['Y'] == 0) & (x_coil_results_s['Z'] == 0)
    ]

    # Extract the maximum Bx value and calculate error
    bx = bx_line['Bx'].max()
    e = target_bx - bx * 1e9  # Target error calculation

    if e <= 0:
        tolerance = 0.005 * bx
        lower_bound = bx - tolerance
        upper_bound = bx + tolerance
        filtered_points = bx_line[
            (bx_line['Bx'] >= lower_bound) & (bx_line['Bx'] <= upper_bound)
        ]

        # Check for contiguity of points
        x_values = filtered_points['X'].sort_values()
        is_contiguous = all(
            (x_values.iloc[i + 1] - x_values.iloc[i]) <= 2 * grid_length_size
            for i in range(len(x_values) - 1)
        )

        # If points are not contiguous, assign an infinite penalty
        if not is_contiguous:
            return 5000  # Penalty

        # Calculate range (a) and return the negative for maximization
        a = abs(filtered_points['X'].max() - filtered_points['X'].min())
        return -a  # Negative since we minimize, but want to maximize range
    else:
        # Penalize for exceeding the target error
        return 5000 + e