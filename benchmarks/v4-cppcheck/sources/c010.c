int f(int i) {
    int number = 10, a = 0;
    for (int count = 0; count < 2; count++) {
        a += (i / number) % 10;
        number = number / 10;
    }
    return a;
}
