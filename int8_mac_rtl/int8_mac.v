`timescale 1ns/1ps

module int8_mac (
    input wire clk,
    input wire rst_n,

    input wire signed [7:0] a,
    input wire signed [7:0] b,

    output reg signed [31:0] acc
);

wire signed [15:0] product;

assign product = a * b;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        acc <= 32'sd0;
    else
        acc <= acc + {{16{product[15]}}, product};
end

endmodule