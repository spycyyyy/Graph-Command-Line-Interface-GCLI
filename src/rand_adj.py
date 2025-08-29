import numpy as np
import pandas as pd

def generate_random_adjacency_matrix_csv(size, filename="adjacency_matrix.csv", weighted=False, mini  = 0, maxi = 11,undirected = False):
    """
    Generates a random adjacency matrix and saves it to a CSV file.

    Args:
        size (int): The number of nodes in the graph (matrix dimension).
        filename (str): The name of the CSV file to save.
        weighted (bool): If True, generates a weighted matrix with random values;
                        otherwise, generates an unweighted matrix with 0s and 1s.
    """
    if weighted:
        # Generate random weights (e.g., between 1 and 10)
        matrix = np.random.randint(int(mini), int(maxi), size=(size, size))
        # Ensure diagonal elements are 0 for no self-loops, or adjust as needed
        np.fill_diagonal(matrix, 0)
    else:
        # Generate binary matrix for unweighted graph
        matrix = np.random.randint(0, 2, size=(size, size))
        # Ensure diagonal elements are 0 for no self-loops
        np.fill_diagonal(matrix, 0)

    if(undirected):
    # For undirected graphs, ensure symmetry
        matrix = (matrix + matrix.T) // 2 # Uncomment for undirected graphs

    rest = np.zeros((size+1,size+1))
    rest[1:,1:] = matrix
    rest[0,:] = np.array(list(map(int,range(size+1))))
    rest[:,0] = np.array(list(map(int,range(size+1))))

    # Create a Pandas DataFrame for easy CSV export
    df = pd.DataFrame(rest.astype(int) )

    # Save to CSV
    df.to_csv(filename, index=False, header=False)
    print(f"File - {filename} generated")

# Example usage:
# Generate an unweighted 5x5 adjacency matrix
size = 10
for i in range(10):
    generate_random_adjacency_matrix_csv(size+i, f"{i}_M{size+i}.csv", weighted=i>5)