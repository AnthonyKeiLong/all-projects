# ==========================================
# PYTHON BASICS VISUALIZER APPLICATION
# ==========================================
# Note: You will need to install matplotlib and networkx:
# pip install matplotlib networkx

import matplotlib.pyplot as plt
import networkx as nx
import sys
import textwrap

def draw_graph(title, edges, node_color='skyblue'):
    """Helper function to draw and display a concept map dynamically."""
    G = nx.DiGraph()
    G.add_edges_from(edges)

    # Wrap text labels so they fit better inside the bubbles
    labels = {node: textwrap.fill(node, width=12) for node in G.nodes()}

    # Set up the visual layout. 
    # Increased figure size and 'k' value to spread nodes further apart.
    plt.figure(figsize=(12, 9))
    pos = nx.spring_layout(G, seed=42, k=1.8, iterations=100) 

    # Draw nodes (larger size), edges, and specific labels
    nx.draw_networkx_nodes(G, pos, node_color=node_color, node_size=5500, edgecolors='black')
    nx.draw_networkx_edges(G, pos, arrowstyle='->', arrowsize=20, edge_color='gray', width=2)
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=9, font_weight='bold', font_family='sans-serif')

    # Display settings
    plt.title(title, fontsize=16, fontweight='bold')
    plt.axis('off')
    plt.tight_layout()
    plt.show()

def show_full_map():
    """Visualizes the high-level Python Basics map."""
    edges = [
        ("Python Basics", "Data Types"),
        ("Python Basics", "Control Flow"),
        ("Python Basics", "Functions"),
        ("Python Basics", "OOP"),
        ("Data Types", "Strings"),
        ("Data Types", "Numbers"),
        ("Data Types", "Collections"),
        ("Control Flow", "Conditionals"),
        ("Control Flow", "Loops")
    ]
    draw_graph("Python Basics: High-Level Overview", edges, 'lightgreen')

def show_data_types():
    """Visualizes a deep dive into Python Data Types."""
    edges = [
        ("Data Types", "Numbers"),
        ("Numbers", "Integer"),
        ("Numbers", "Float"),
        ("Data Types", "Text"),
        ("Text", "String"),
        ("Data Types", "Collections"),
        ("Collections", "List (Mutable)"),
        ("Collections", "Tuple (Immutable)"),
        ("Collections", "Dict (Key-Value)"),
        ("Data Types", "Boolean"),
        ("Boolean", "True"),
        ("Boolean", "False")
    ]
    draw_graph("Deep Dive: Python Data Types", edges, 'skyblue')

def show_control_flow():
    """Visualizes a deep dive into Python Control Flow."""
    edges = [
        ("Control Flow", "Conditionals"),
        ("Conditionals", "if"),
        ("Conditionals", "elif"),
        ("Conditionals", "else"),
        ("Control Flow", "Loops"),
        ("Loops", "for loop"),
        ("Loops", "while loop"),
        ("Loops", "Loop Control"),
        ("Loop Control", "break"),
        ("Loop Control", "continue")
    ]
    draw_graph("Deep Dive: Control Flow", edges, 'salmon')

def main():
    """Main application loop."""
    while True:
        print("\n" + "="*40)
        print("🐍 PYTHON BASICS VISUALIZER APP 🐍")
        print("="*40)
        print("Select a topic to visualize:")
        print("1. High-Level Concept Map")
        print("2. Deep Dive: Data Types")
        print("3. Deep Dive: Control Flow")
        print("4. Exit Application")
        
        choice = input("\nEnter your choice (1-4): ")
        
        if choice == '1':
            print("Generating High-Level Map... (Close the window to return to menu)")
            show_full_map()
        elif choice == '2':
            print("Generating Data Types Map... (Close the window to return to menu)")
            show_data_types()
        elif choice == '3':
            print("Generating Control Flow Map... (Close the window to return to menu)")
            show_control_flow()
        elif choice == '4':
            print("Exiting application. Goodbye!")
            sys.exit()
        else:
            print("❌ Invalid choice. Please enter a number between 1 and 4.")

if __name__ == "__main__":
    main()