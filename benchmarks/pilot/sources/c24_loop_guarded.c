int case24(int x) {
    int denominator = x;
    while (denominator > 0)
        denominator--;
    if (denominator == 0)
        return 0;
    return 42 / denominator;
}

