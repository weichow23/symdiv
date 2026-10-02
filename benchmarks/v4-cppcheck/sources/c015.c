int main() {
    return _Generic((0), int: (42) / (0), default: 0);
}
