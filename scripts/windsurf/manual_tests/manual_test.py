def hello_world():
    """A simple hello world function."""
    print("Hello from Manual Test!")
    return "Success!"


def add_numbers(a, b):
    """Add two numbers and return the result."""
    return a + b


if __name__ == "__main__":
    # Test the functions
    result = hello_world()
    numbers = add_numbers(10, 5)
    print(f"10 + 5 = {numbers}")
    print("Manual file creation test completed!")
