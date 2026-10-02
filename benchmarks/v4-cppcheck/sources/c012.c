int f(int len) {
    int sz = sizeof(void*[255]) / 255;
    int x = len % sz;
    return x;
}
