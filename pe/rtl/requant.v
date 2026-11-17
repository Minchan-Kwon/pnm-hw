// Author: Minchan Kwon
// Requantization unit: out = clamp(round(in * scale), -MAX, +MAX)
// scale is FP16, applied with integer hardware only:
//   FP16 value = significand(11b) * 2^(exponent - 25)
//   -> multiply by the significand, then arithmetic right shift by (25 - exponent)
// Rounding: round half up (floor(x + 0.5))
// Assumes scale is positive and < 1024 (exponent field <= 24); the sign bit is ignored.
// Larger scales (incl. Inf/NaN) saturate the output.

module requant #(
    parameter IN_WIDTH  = 32,  // Input width (INT32 accumulation or INT16 product)
    parameter OUT_WIDTH = 8    // Output width (INT8)
)(
    input  signed [IN_WIDTH-1:0]  in,
    input         [15:0]          scale,  // FP16 requantization scale
    output signed [OUT_WIDTH-1:0] out
);
    localparam PROD_WIDTH = IN_WIDTH + 12;  // in * significand (11b + 1 sign bit)
    localparam signed [PROD_WIDTH-1:0] MAX = (1 << (OUT_WIDTH-1)) - 1;  // +127
    localparam signed [PROD_WIDTH-1:0] MIN = -MAX;                      // -127 (symmetric)

    // FP16 decode
    wire [4:0] exponent  = scale[14:10];
    wire [9:0] mantissa  = scale[9:0];
    wire       subnormal = (exponent == 5'd0);
    wire       too_large = (exponent >= 5'd25);  // scale >= 1024: not supported, saturate

    wire [10:0] significand = {~subnormal, mantissa};                 // Hidden 1 for normal numbers
    wire  [4:0] shift       = subnormal ? 5'd24 : (5'd25 - exponent); // 1..24 when !too_large

    // Multiply, round half up, shift
    wire signed [PROD_WIDTH-1:0] scaled  = in * $signed({1'b0, significand});
    wire signed [PROD_WIDTH-1:0] half    = {{(PROD_WIDTH-1){1'b0}}, 1'b1} << (shift - 5'd1);
    wire signed [PROD_WIDTH-1:0] rounded = (scaled + half) >>> shift;

    // Clamp to [-MAX, +MAX]
    wire signed [PROD_WIDTH-1:0] saturated = (in > 0) ? MAX : (in < 0) ? MIN : {PROD_WIDTH{1'b0}};
    wire signed [PROD_WIDTH-1:0] clamped   = too_large     ? saturated :
                                             (rounded > MAX) ? MAX :
                                             (rounded < MIN) ? MIN : rounded;

    assign out = clamped[OUT_WIDTH-1:0];

endmodule
