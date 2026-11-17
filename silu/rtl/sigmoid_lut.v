// Author: Minchan Kwon
// sigmoid_lut
// The coefficients of the piece-wise linear approximations

module sigmoid_lut (abs_x, in_range, htan);
`include "silu_params.vh"
    input  wire           [XW-1:0] abs_x;
    input  wire                    in_range;
    output wire signed [HTANW-1:0] htan;

    wire [SEGB-1:0] seg = abs_x[XW-1:SEGLSB];
    wire [OFFW-1:0] off = abs_x[SEGLSB-1:DROP];

    wire [SLOPEW+ICPTW-1:0]  coef      = htan_coef(seg);
    wire signed [SLOPEW-1:0] slope     = coef[SLOPEW+ICPTW-1:ICPTW];
    wire signed [ICPTW-1:0]  intercept = coef[ICPTW-1:0];

    localparam integer LINEW = ((SLOPEW + OFFW + 1) > ICPTW ? (SLOPEW + OFFW + 1) : ICPTW) + 1;
    wire signed [LINEW-1:0] htan_line_g = slope * $signed({1'b0, off}) + intercept;
    wire signed [LINEW-1:0] htan_line   = htan_line_g >>> GB;

    assign htan = in_range ? htan_line[HTANW-1:0] : (1 <<< (HTANFB - 1));
endmodule