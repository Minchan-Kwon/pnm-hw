// Author: Minchan Kwon
// SiLU activation accelerator for MoE inference on SSDs
// SPECs to be decided

module silu_a_top (clk, rstn, q_in, scale_in, y);
`include "silu_params.vh"
    input  wire        clk;
    input  wire        rstn;
    input  wire [7:0]  q_in;
    input  wire [15:0] scale_in;
    output reg  [7:0]  y;

    reg signed [7:0]  q;
    reg        [15:0] scale;
    always @(posedge clk or negedge rstn)
        if (!rstn) begin q <= 8'sd0; scale <= 16'd0; end
        else       begin q <= q_in;  scale <= scale_in; end

    wire [4:0]  exponent;
    wire [10:0] mantissa;
    wire invalid, relu, half;
    scale_decoder u_dec (.scale(scale), .exponent(exponent), .mantissa(mantissa), .invalid(invalid), .relu(relu), .half(half));

    wire [7:0] abs_q;  wire [XW-1:0] abs_x;  wire in_range;
    abs_x u_abs (.q(q), .exponent(exponent), .mantissa(mantissa), .abs_q(abs_q), .abs_x(abs_x), .in_range(in_range));

    wire signed [HTANW-1:0] htan;
    sigmoid_lut u_lut (.abs_x(abs_x), .in_range(in_range), .htan(htan));

    wire [7:0] y_next;
    silu_out u_out (.q(q), .abs_q(abs_q), .htan(htan), .invalid(invalid), .relu(relu), .half(half), .y(y_next));

    always @(posedge clk or negedge rstn) begin
        if (!rstn) y <= 8'd0;
        else       y <= y_next;
    end
endmodule