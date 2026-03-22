
#include <stdio.h>
int main() {
    long long iterations = 10000000;
    long long inside = 0;
    for (long long i = 0; i < iterations; i++) {
        long long x = (i * 1103515245 + 12345) % 32768;
        long long y = (i * 22695477 + 1) % 32768;
        if ((x*x + y*y) <= 1073741824LL) inside++;
    }
    printf("Estimated Pi * 1000: %lld\n", (4000 * inside) / iterations);
    return 0;
}
