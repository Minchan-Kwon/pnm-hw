// Author: Minchan Kwon
// abs_x
// Computes the absolute value of x and outputs in Q3.FXA format.
// |x| = abs_q * {mantissa * 2^(-10)} * 2^(exponent-15) * 2^FXA
// where 2^(-10) comes from the mantissa, which is Q1.10 format.
// 15 is the bias in FP16 and FXA is the width decimal points. 

module abs_x (q, exponent, mantissa, abs_q, abs_x, in_range);
`include "silu_params.vh"
    input  wire signed [7:0]  q;
    input  wire        [4:0]  exponent;
    input  wire        [10:0] mantissa;
    output wire        [7:0]  abs_q;
    output wire     [XW-1:0]  abs_x;
    output wire               in_range;

    assign abs_q = q[7] ? (~q + 8'b1) : q;

    wire [18:0] P  = abs_q * mantissa;
    wire [4:0]  rs = 5'd25 - XFB - exponent;
    // Store |x| in Q3.XFB format
    wire [19:0] P2 = {P, 1'b0} + (20'b1 << rs);
    wire [19:0] af = P2 >> (rs + 5'b1);

    assign in_range = (af < XMAX);
    assign abs_x    = af[XW-1:0];
endmodule