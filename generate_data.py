import os
import numpy as np
import pyvista as pv

# Ensure target directories exist
os.makedirs("dataset/train/safe", exist_ok=True)
os.makedirs("dataset/train/not_safe", exist_ok=True)

def generate_synthetic_terrain():
    # Start PyVista off-screen plotter
    plotter = pv.Plotter(off_screen=True, window_size=(224, 224))
    
    # 1. Generate "Safe" Flat/Gently Rolling Plains
    print("Generating safe terrain samples...")
    for i in range(25):
        # FIXED: Use i_size and j_size instead of size
        plane = pv.Plane(i_resolution=20, j_resolution=20, i_size=10, j_size=10)
        points = plane.points
        # Add minimal height variation
        points[:, 2] = np.sin(points[:, 0] + i) * 0.1
        plane.points = points
        
        plotter.clear()
        plotter.add_mesh(plane, color="gray", smooth_shading=True)
        plotter.view_isometric()
        
        filename = f"dataset/train/safe/safe_terrain_{i}.png"
        plotter.screenshot(filename)

    # 2. Generate "Not Safe" High-Hazard / Cratered Terrain
    print("Generating hazard terrain samples...")
    for i in range(25):
        # FIXED: Use i_size and j_size instead of size
        plane = pv.Plane(i_resolution=30, j_resolution=30, i_size=10, j_size=10)
        points = plane.points
        
        # Simulate sharp crater-like depressions
        center_x, center_y = np.random.uniform(-3, 3), np.random.uniform(-3, 3)
        dist = np.sqrt((points[:, 0] - center_x)**2 + (points[:, 1] - center_y)**2)
        points[:, 2] = -1.5 * np.exp(-dist**2 / 2.0) + np.random.normal(0, 0.2, points.shape[0])
        
        plane.points = points
        
        plotter.clear()
        plotter.add_mesh(plane, color="saddlebrown", smooth_shading=False)
        plotter.view_isometric()
        
        filename = f"dataset/train/not_safe/hazard_terrain_{i}.png"
        plotter.screenshot(filename)

    plotter.close()
    print("Synthetic lunar data generation complete!")

if __name__ == "__main__":
    generate_synthetic_terrain()