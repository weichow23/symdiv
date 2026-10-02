int f(int i) {
    int number = 10, a = 0;
    for (int count = 0; count < 2; count++) {
        int x = number / 10;
        a += (i / number) % 10;
        number = x;
    }
    return a;
}
