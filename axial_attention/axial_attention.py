import torch
from torch import nn
from operator import itemgetter

def map_el_ind(arr, ind):
    return list(map(itemgetter(ind), arr))

def sort_and_return_indices(arr):
    indices = [ind for ind in range(len(arr))]
    arr = zip(arr, indices)
    arr = sorted(arr)
    return map_el_ind(arr, 0), map_el_ind(arr, 1)

# calculates the permutation to bring the input tensor to something attend-able
# also calculates the inverse permutation to bring the tensor back to its original shape

def calculate_permutations(num_dimensions, emb_dim):
    total_dimensions = num_dimensions + 2
    emb_dim = emb_dim if emb_dim > 0 else (emb_dim + total_dimensions)
    axial_dims = [ind for ind in range(1, total_dimensions) if ind != emb_dim]

    permutations = []

    for axial_dim in axial_dims:
        last_two_dims = [axial_dim, emb_dim]
        dims_rest = set(range(0, num_dimensions + 2)) - set(last_two_dims)
        permutation = [*dims_rest, *last_two_dims]
        _, inv_permutation = sort_and_return_indices(permutation)
        permutations.append((permutation, inv_permutation))
      
    return permutations

# classic multi-head attention

class SelfAttention(nn.Module):
    def __init__(self, dim, heads):
        super().__init__()
        self.heads = heads
        self.to_qkv = nn.Linear(dim, 3 * dim, bias = False)
        self.to_out = nn.Linear(dim, dim, bias = False)

    def forward(self, x):
        b, t, d, h = *x.shape, self.heads
        q, k, v = self.to_qkv(x).chunk(3, dim=-1)
        merge_heads = lambda x: x.reshape(b, t, h, -1).transpose(1, 2).reshape(b * h, t, -1)
        q, k, v = map(merge_heads, (q, k, v))
        dots = torch.einsum('bie,bje->bij', q, k) * (d ** -0.5)
        out = torch.einsum('bij,bje->bie', dots, v)
        out = out.reshape(b, h, t, -1).transpose(1, 2).reshape(b, t, -1)
        out = self.to_out(out)
        return out

# axial attention class

class AxialAttention(nn.Module):
    def __init__(self, dim, num_dimensions = 2, heads = 8, dim_index = -1):
        assert (dim % heads) == 0, 'hidden dimension must be divisible by number of heads'
        super().__init__()
        self.dim = dim
        self.total_dimensions = num_dimensions + 2
        self.dim_index = dim_index if dim_index > 0 else (dim_index + self.total_dimensions)
        self.axial_attentions = nn.ModuleList([SelfAttention(dim, heads) for _ in range(num_dimensions)])
        self.permutations = calculate_permutations(num_dimensions, dim_index)

    def forward(self, x):
        assert len(x.shape) == self.total_dimensions, 'input tensor does not have the correct number of dimensions'
        assert x.shape[self.dim_index] == self.dim, 'input tensor does not have the correct input dimension'

        out = []

        for axial_attn, (permutation, inv_permutation) in zip(self.axial_attentions, self.permutations):
            # permute to bring embedding dimension to last, axial dimension to second to last
            axial = x.permute(*permutation)

            shape = axial.shape
            *_, t, d = shape

            # merge all but axial dimension
            axial = axial.reshape(-1, t, d)

            # attention
            axial = axial_attn(axial)

            # restore to original shape and permutation
            axial = axial.reshape(*shape)
            axial = axial.permute(*inv_permutation)

            out.append(axial)

        return sum(out)
