#include <cassert>
#include <numeric>
#include <vector>
#include "../backends/stable-diffusion.cpp/src/model/upscaler/esrgan_layout.hpp"

int main() {
    std::vector<float> input(64);
    std::iota(input.begin(), input.end(), 0.0f);
    auto result = esrgan_pixel_unshuffle(input.data(), 4, 4, 2, 2, 2);
    const std::vector<float> expected = {
        0,2,8,10, 1,3,9,11, 4,6,12,14, 5,7,13,15,
        16,18,24,26, 17,19,25,27, 20,22,28,30, 21,23,29,31,
        32,34,40,42, 33,35,41,43, 36,38,44,46, 37,39,45,47,
        48,50,56,58, 49,51,57,59, 52,54,60,62, 53,55,61,63
    };
    assert(result == expected);
    assert(esrgan_pixel_unshuffle(input.data(),4,4,2,2,1) == input);
    bool rejected = false;
    try { esrgan_pixel_unshuffle(input.data(),3,4,1,1,2); }
    catch (const std::invalid_argument&) { rejected = true; }
    assert(rejected);
}
